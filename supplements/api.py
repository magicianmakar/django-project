import json
from decimal import Decimal
from io import BytesIO

from django.conf import settings
from django.contrib.auth.models import User
from django.db.models import Q
from django.urls import reverse
from django.utils.crypto import get_random_string
from django.utils.text import slugify
from django.views.generic import View

from pdfrw import PdfWriter

from leadgalaxy.utils import aws_s3_upload
from lib.exceptions import capture_exception, capture_message
from shopified_core import permissions
from shopified_core.mixins import ApiResponseMixin
from shopified_core.utils import get_store_api, safe_int

from .lib.image import get_order_number_label
from .lib.shipstation import create_shipstation_order, prepare_shipstation_data
from .models import Payout, PLSOrder, PLSOrderLine, UserSupplement, UserSupplementLabel
from .utils import user_can_download_label
from .utils.payment import Util, get_shipping_cost


class SupplementsApi(ApiResponseMixin, View):
    http_method_names = ['get', 'post', 'delete']

    def post_make_payment(self, request, user, data):
        util = Util()
        store = util.get_store(data['store_id'], data['store_type'])
        permissions.user_can_view(user, store)

        util.store = store

        success = error = invalid_country = inventory_error = 0
        success_ids = []

        info = util.prepare_data(request, data['order_data_ids'])
        orders, line_items, order_data_ids, error = info

        for order_id, order in orders.items():
            try:
                province = order['shipping_address']['province_code']
            except:
                province = order['shipping_address']['province']
            order_info = (order['order_number'], order_id, order['shipping_address']['country_code'],
                          province)
            order_line_items = line_items[order_id]

            shipping_country = order['shipping_address']['country']
            shipping_country_province = slugify(order['shipping_address']['country_code'] + "-" + str(order['shipping_address']['province']))

            quantity_dict = {}
            for line in order_line_items:
                target_countries = []
                user_supplement = line['user_supplement']
                if user_supplement.is_deleted:
                    data = {
                        'error': 'rejected',
                        'msg': 'Your order contains deleted product & has been rejected.',
                    }
                    return self.api_success(data)

                shipping_countries = user_supplement.shipping_countries
                target_countries.extend(shipping_countries)
                target_countries = set(target_countries)

                if target_countries and shipping_country not in set(target_countries) \
                        and shipping_country_province not in set(target_countries):
                    invalid_country += 1

                if user_supplement in quantity_dict:
                    quantity_dict[user_supplement] += int(line['quantity'])
                else:
                    quantity_dict[user_supplement] = int(line['quantity'])

            for user_supplement, qty in quantity_dict.items():
                if user_supplement.pl_supplement.inventory < qty:
                    inventory_error += 1

            if invalid_country > 0 or inventory_error > 0:
                continue

            try:
                pls_order = util.make_payment(
                    order_info,
                    order_line_items,
                    user.models_user,
                )
            except Exception:
                error += len(order_line_items)
                capture_exception(level='warning')
            else:
                shipstation_data = prepare_shipstation_data(pls_order,
                                                            order,
                                                            order_line_items,
                                                            )
                create_shipstation_order(pls_order, shipstation_data)

                StoreApi = get_store_api(data['store_type'])
                for item in pls_order.order_items.all():
                    if item.shipstation_key:
                        data = {
                            'store': store.id,
                            'order_id': item.store_order_id,
                            'line_id': item.line_id,
                            'aliexpress_order_id': str(pls_order.get_dropified_source_id()),
                            'source_type': 'supplements'
                        }

                        api_result = StoreApi.post_order_fulfill(request, user, data)
                        if api_result.status_code != 200:
                            error += 1
                            capture_message('Unable to track supplement', extra={
                                'api_result': json.loads(api_result.content.decode("utf-8")),
                                'api_data': data
                            }, level='warning')

                success += len(order_line_items)
                success_ids.extend([
                    {'id': i, 'status': pls_order.status_string}
                    for i in order_data_ids[order_id]
                ])

        data = {
            'success': success,
            'error': error,
            'successIds': success_ids,
            'invalidCountry': invalid_country,
            'inventoryError': inventory_error,
        }
        return self.api_success(data)

    def post_mark_printed(self, request, user, data):
        util = Util()
        line_id = data['item-id']
        util.mark_label_printed(line_id)
        return self.api_success()

    def post_bulk_print(self, request, user, data):
        util = Util()
        label_writer = PdfWriter()
        for line_id in data['item-ids']:
            line_item = util.mark_label_printed(line_id)
            label_pdf = get_order_number_label(line_item)
            for _ in range(line_item.quantity):
                label_writer.addpages(label_pdf.pages)

        output = BytesIO()
        label_writer.write(output)

        if not output.tell():
            data = {'download-url': ''}
            return self.api_success(data)

        output.seek(0)

        random_name = get_random_string(length=10)
        pdf_name = (f'uploads/u{user.id}/all_labels/{random_name}.pdf')

        url = aws_s3_upload(
            filename=pdf_name,
            fp=output,
            mimetype='application/pdf',
            bucket_name=settings.S3_UPLOADS_BUCKET
        )

        data = {'download-url': url}
        return self.api_success(data)

    def post_bulk_mark(self, request, user, data):
        util = Util()
        for line_id in data['item-ids']:
            util.mark_label_printed(line_id)

        return self.api_success()

    def post_bulk_unmark(self, request, user, data):
        util = Util()
        for line_id in data['item-ids']:
            util.mark_label_not_printed(line_id)

        return self.api_success()

    def post_order_payout(self, request, user, data):
        order_id = data['order-id']
        try:
            order = PLSOrder.objects.get(id=order_id)
        except PLSOrder.DoesNotExist:
            return self.api_error('Order not found', status=404)

        reference_number = data['reference-number']
        if reference_number:
            try:
                payout = Payout.objects.get(reference_number=reference_number)
            except Payout.DoesNotExist:
                return self.api_error('Payout not found', status=404)

            order.payout = payout
        else:
            order.payout = None
        order.save()

        return self.api_success()

    def post_shipping_cost_payout(self, request, user, data):
        payout_id = data['payout_id']
        shipping_cost = data['cost']
        try:
            payout = Payout.objects.get(id=payout_id)
        except Payout.DoesNotExist:
            return self.api_error('Payout not found', status=404)

        payout.shipping_cost = int(shipping_cost) * 100
        payout.save()

        return self.api_success()

    def post_calculate_shipping_cost(self, request, user, data):
        StoreApi = get_store_api(data['store_type'])

        shipping_info = {}
        for order_data_id in data['order_data_ids']:
            store_id, order_id, line_id = order_data_id.split('_')
            api_result = StoreApi.get_order_data(request, request.user, {'order': order_data_id, 'original': '1'})
            if api_result.status_code == 404:
                return self.api_error("Please reload the page and try again", status=404)

            order_data = json.loads(api_result.content.decode("utf-8"))
            if order_data.get('supplier_type') != 'pls':
                return self.api_error("Selected item is not a supplement", status=404)

            if order_id not in shipping_info:
                shipping_info[order_id] = {'total_weight': Decimal(0)}
            shipping_info[order_id]['country_code'] = order_data['shipping_address']['country_code']
            shipping_info[order_id]['province_code'] = order_data['shipping_address']['province_code']

            if order_data['is_bundle']:
                for b_product in order_data['products']:
                    shipping_info[order_id]['total_weight'] += Decimal(b_product.get('weight') or 0)
            else:
                # Can be None or False
                shipping_info[order_id]['total_weight'] += Decimal(order_data.get('weight') or 0)

        # Don't use multiple shipping costs for now
        shipping_info = list(shipping_info.values())[0]

        shipping_price = get_shipping_cost(
            shipping_info['country_code'],
            shipping_info['province_code'],
            shipping_info['total_weight']
        )

        data = {'shipping_cost': shipping_price}
        if shipping_price is False:
            return self.api_error('Error calculating shipping', status=500)
        else:
            return self.api_success(data)

    def post_sync_order(self, request, user, data):
        order = PLSOrder.objects.filter(
            Q(stripe_transaction_id=data.get('source_id'))
            | Q(id=data.get('source_id')),
            user=request.user.models_user
        ).first()

        if order is None:
            return self.api_error('Order not found', status=404)

        status = {
            PLSOrder.PENDING: 'D_PENDING_PAYMENT',
            PLSOrder.PAID: 'D_PAID',
            PLSOrder.SHIPPED: 'D_SHIPPED',
        }.get(order.status, 'PLACE_ORDER_SUCCESS')

        total_price = Decimal(order.amount) / Decimal(100)
        shipping_price = Decimal(order.shipping_price) / Decimal(100)
        products_price = total_price - shipping_price

        tracking_numbers = []
        for item in order.order_items.values('tracking_number'):
            if item['tracking_number'] and item['tracking_number'] not in tracking_numbers:
                tracking_numbers.append(item['tracking_number'])
        tracking_number = ','.join(tracking_numbers)
        return self.api_success({
            'details': {
                'status': status,
                'orderStatus': status,  # Mock extension
                'tracking_number': tracking_number,
                'order_details': {'cost': {
                    'total': str(total_price.quantize(Decimal('0.01'))),
                    'products': str(products_price.quantize(Decimal('0.01'))),
                    'shipping': str(shipping_price.quantize(Decimal('0.01'))),
                }},
                'source_id': order.get_dropified_source_id(),
            }
        })

    def post_delete_usersupplement(self, request, user, data):
        if request.user.profile.is_black or request.user.can('pls.use'):
            pk = safe_int(data['product'])
            try:
                product = UserSupplement.objects.get(id=pk, user=request.user.models_user)
            except UserSupplement.DoesNotExist:
                return self.api_error('Supplement not found', status=404)

            product.is_deleted = True
            product.save(update_fields=['is_deleted'])
            return self.api_success()
        else:
            raise permissions.PermissionDenied()

    def post_mark_usersupplement_unread(self, request, user, data):
        if request.user.can('pls_admin.use') or request.user.can('pls_staff.use'):
            pk = safe_int(data['item_id'])
            try:
                product = UserSupplement.objects.get(id=pk)
            except UserSupplement.DoesNotExist:
                return self.api_error('Supplement not found', status=404)

            product.seen_users = ''
            product.save(update_fields=['seen_users'])
            return self.api_success()
        else:
            raise permissions.PermissionDenied()

    def get_order_line_info(self, request, user, data):
        item_id = safe_int(data.get('item_id'))

        try:
            order_line = PLSOrderLine.objects.get(pk=item_id)
        except PLSOrderLine.DoesNotExist:
            return self.api_error('Order item not found', status=404)

        label = order_line.label

        if not user_can_download_label(user, label):
            raise permissions.PermissionDenied()

        user_supplement = label.user_supplement
        latest_label = user_supplement.labels.order_by('-created_at').first()
        label_count = user_supplement.labels.count()
        newer_available = label_count > 1 and not label == latest_label
        current_is_rejected = label.status == UserSupplementLabel.REJECTED
        latest_is_approved = latest_label.status == UserSupplementLabel.APPROVED
        label_url = reverse('pls:generate_label', args=(item_id,))
        latest_label_url = label_url + '?use_latest=1'

        return self.api_success({
            'item_id': item_id,
            'newer_available': newer_available,
            'current_is_rejected': current_is_rejected,
            'latest_is_approved': latest_is_approved,
            'label_url': label_url,
            'latest_label_url': latest_label_url,
        })

    def get_billing_info(self, request, user, data):
        if request.user.profile.is_black or request.user.can('pls.use'):
            # TODO: AUTHNET ROLLBACK
            return self.api_success({'success': 1, 'error': 0})
            success = error = 0
            try:
                user.authorize_net_customer
                success += 1
            except User.authorize_net_customer.RelatedObjectDoesNotExist:
                error += 1

            return self.api_success({
                'success': success,
                'error': error,
            })
        else:
            raise permissions.PermissionDenied()
