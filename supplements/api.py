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
from django.utils import timezone

from pdfrw import PdfWriter

from leadgalaxy.utils import aws_s3_upload
from lib.exceptions import capture_exception, capture_message
from product_common.models import ProductSupplier
from shopified_core import permissions
from shopified_core.mixins import ApiResponseMixin

from .lib.image import get_order_number_label
from .lib.shipstation import create_shipstation_order, prepare_shipstation_data
from .models import Payout, PLSOrder, PLSOrderLine, UserSupplement, UserSupplementLabel, BasketItem, PLSupplement
from .utils import user_can_download_label
from .utils.payment import Util, get_shipping_costs
from .utils.basket import BasketStore
from shopified_core.utils import (
    get_store_api,
    safe_int,
    safe_float,
    clean_tracking_number,
    CancelledOrderAlert
)
from shopified_core.shipping_helper import province_code_from_name, country_from_code
from django.db.models import Avg
from my_basket.models import BasketOrderTrack
from fulfilment_fee.utils import process_sale_transaction_fee


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
                          province, data.get('shipping_service'))
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

                if isinstance(shipping_country, list):
                    for country in shipping_country:
                        if country not in target_countries:
                            invalid_country += 1
                elif target_countries and shipping_country not in target_countries \
                        and shipping_country_province not in target_countries:
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
                                                            service_code=data.get('shipping_service'))
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

        try:
            payout.shipping_cost = int(shipping_cost) * 100
        except ValueError:
            payout.shipping_cost = None
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

        shippings = get_shipping_costs(
            shipping_info['country_code'],
            shipping_info['province_code'],
            shipping_info['total_weight']
        )

        if isinstance(shippings, (bool, str)):
            error_message = not shippings and 'Error calculating shipping' or shippings
            return self.api_error(error_message, status=500)
        else:
            return self.api_success({'shippings': shippings})

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
                    'currency': 'USD',
                }},
                'source_id': order.get_dropified_source_id(),
            }
        })

    def post_delete_usersupplement(self, request, user, data):
        if request.user.can('pls.use'):
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
        if request.user.can('pls.use'):
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

    def get_order_lines(self, request, user, data):
        order_id = safe_int(data.get('order_id'))
        try:
            order = PLSOrder.objects.get(id=order_id)
        except PLSOrder.DoesNotExist:
            return self.api_error('Order not found', status=404)

        line_items = [dict(
            id=i.id,
            sku=i.label.sku,
            quantity=i.quantity,
            supplement=i.label.user_supplement.to_dict(),
            line_total="${:.2f}".format((i.amount * i.quantity) / 100.)
        ) for i in order.order_items.all()]

        return self.api_success({'items': line_items})

    def post_create_payouts(self, request, user, data):
        if not request.user.can('pls_admin.use'):
            raise permissions.PermissionDenied()

        supplier_ids = data.keys()
        for id in supplier_ids:
            supplier = ProductSupplier.objects.get(id=id)
            if supplier.is_shipping_supplier:
                line_items = PLSOrderLine.objects.filter(pls_order__is_fulfilled=True,
                                                         shipping_payout__isnull=True)
                if line_items.count():
                    payout = Payout.objects.create(reference_number=data[id],
                                                   supplier=supplier)
                    line_items.update(shipping_payout=payout)
            else:
                line_items = PLSOrderLine.objects.filter(pls_order__is_fulfilled=True,
                                                         label__user_supplement__pl_supplement__supplier=supplier,
                                                         line_payout__isnull=True)
                if line_items.count():
                    payout = Payout.objects.create(reference_number=data[id],
                                                   supplier=supplier)
                    line_items.update(line_payout=payout)

        return self.api_success()

    def post_add_basket(self, request, user, data):
        product_id = data['product-id']

        try:
            user_supplement = user.pl_supplements.get(id=product_id)
        except UserSupplement.DoesNotExist:
            return self.api_error('Product not found', status=404)

        if not user_supplement.current_label or user_supplement.current_label.status != "approved":
            return self.api_error('Label not approved yet', status=500)

        try:
            basket_item = user.basket_items.get(user_supplement=user_supplement)
            basket_item.quantity += 1
        except BasketItem.DoesNotExist:
            basket_item = BasketItem()
            basket_item.quantity = 1
            basket_item.user = user
            basket_item.user_supplement = user_supplement
        basket_item.save()

        return self.api_success({'basket-id': basket_item.id})

    def post_update_basket(self, request, user, data):
        basket_id = data['basket-id']
        quantity = data['quantity']

        try:
            basket_item = user.basket_items.get(id=basket_id)
            basket_item.quantity = quantity

            if safe_int(basket_item.quantity) <= 0:
                basket_item.delete()
            else:
                basket_item.save()

            return self.api_success({'basket-id': basket_item.id,
                                     'quantity': basket_item.quantity,
                                     'total_price': basket_item.total_price()})
        except BasketItem.DoesNotExist:
            return self.api_error('Item not found', status=404)

    def get_basket_total(self, request, user, data):
        total = 0
        basket_items = user.basket_items.all()
        for basket_item in basket_items:
            total += safe_float(basket_item.total_price())
        total = '%.02f' % total
        return self.api_success({'total': total})

    def post_basket_calculate_shipping_cost(self, request, user, data):
        country_code = data['country_code']
        province = data['province']

        province_code = province_code_from_name(country_code, province)

        basket_items = user.basket_items.all()
        total_weight = 0
        for basket_item in basket_items:
            total_weight += basket_item.user_supplement.pl_supplement.weight * basket_item.quantity

        shippings = get_shipping_costs(
            country_code,
            province_code,
            total_weight
        )

        if isinstance(shippings, (bool, str)):
            error_message = not shippings and 'Error calculating shipping' or shippings
            return self.api_error(error_message, status=500)
        else:
            return self.api_success({'shippings': shippings})

    def post_basket_make_payment(self, request, user, data):
        country_code = data['shipping_country']
        province = data['shipping_state']
        billing_country_code = data['billing_country']
        billing_province = data['billing_state']

        if user.basket_items.count() <= 0:
            return self.api_error("No items in basket", status=500)

        billing_province_code = province_code_from_name(billing_country_code, billing_province)

        # fix "False" for shipstation
        if not billing_province_code:
            billing_province_code = ""
        province_code = province_code_from_name(country_code, province)
        if not province_code:
            province_code = ""

        checkout_data = data.copy()
        checkout_data['billing_state_code'] = billing_province_code
        checkout_data['shipping_state_code'] = province_code
        billing_country = country_from_code(billing_country_code)
        checkout_data['billing_country'] = billing_country
        checkout_data['billing_country_code'] = country_code
        shipping_country = country_from_code(country_code)
        checkout_data['shipping_country'] = shipping_country
        checkout_data['shipping_country_code'] = country_code

        order_line_items = []

        # check quantity
        basket_items_qty = user.basket_items.values('user_supplement__pl_supplement').annotate(total_qty=Avg('quantity'))
        for plsupplement_item in basket_items_qty:
            pl_supplement = PLSupplement.objects.get(id=plsupplement_item['user_supplement__pl_supplement'])
            if plsupplement_item['user_supplement__pl_supplement'] > pl_supplement.inventory:
                return self.api_error("{} doesn't have that much in stock".format(pl_supplement.title),
                                      status=500)

        basket_items = user.basket_items.all()
        for basket_item in basket_items:
            # checking target country per line
            target_countries = []
            shipping_countries = basket_item.user_supplement.shipping_countries
            target_countries.extend(shipping_countries)
            target_countries = set(target_countries)
            if target_countries and shipping_country not in set(target_countries) \
                    and province not in set(target_countries):
                return self.api_error("{} not ships to {}".format(basket_item.user_supplement.title, shipping_country), status=500)

            order_line = dict()
            order_line['id'] = basket_item.id
            order_line['quantity'] = basket_item.quantity
            order_line['price'] = basket_item.user_supplement.pl_supplement.cost_price
            order_line['user_supplement'] = basket_item.user_supplement
            order_line['label'] = basket_item.user_supplement.current_label
            order_line['title'] = basket_item.user_supplement.title
            order_line['sku'] = basket_item.user_supplement.pl_supplement.shipstation_sku

            order_line_items.append(order_line)

        util = Util()
        util.store = BasketStore()
        checkout_data['line_items'] = order_line_items
        basket_order = util.store.create_order(user, checkout_data)
        order_info = (basket_order.id, basket_order.id, country_code,
                      province_code, None)
        order = basket_order.get_order()
        try:
            pls_order = util.make_payment(
                order_info,
                order_line_items,
                user.models_user,
            )
        except Exception:
            basket_order.delete()
            capture_exception(level='warning')
            return self.api_error("Payment Error", status=500)
        else:
            # clear basket items
            user.basket_items.all().delete()

            shipstation_data = prepare_shipstation_data(pls_order,
                                                        order,
                                                        order_line_items,
                                                        service_code=data.get('shipping_service'))
            create_shipstation_order(pls_order, shipstation_data)
            basket_order.set_paid(True)
            basket_order.save()

            util.store.create_order_tracks(pls_order, basket_order)

        success_data = {
            'success': "Order has been sent to fulfilment",
        }
        return self.api_success(success_data)


# this class can be moved to utils/pasket.py or separate file
class BasketApi(ApiResponseMixin, View):
    http_method_names = ['get', 'post', 'delete']

    def post_order_fulfill_update(self, request, user, data):
        if data.get('store'):
            store = BasketStore.objects.get(id=safe_int(data['store']))
            if not user.can('place_orders.sub', store):
                return self.api_error('Permission Denied', status=403)
        try:
            order = BasketOrderTrack.objects.get(id=data.get('order'))
            permissions.user_can_edit(user, order)
        except BasketOrderTrack.DoesNotExist:
            return self.api_error('Order Not Found', status=404)

        cancelled_order_alert = CancelledOrderAlert(user.models_user,
                                                    data.get('source_id'),
                                                    data.get('end_reason'),
                                                    order.source_status_details,
                                                    order)

        order.source_status = data.get('status')

        # using ShipStation status as order fulfilment flag
        if data.get('status') == "D_SHIPPED":
            order.basket_order_status = "fulfilled"
        order.source_tracking = clean_tracking_number(data.get('tracking_number'))
        order.status_updated_at = timezone.now()

        try:
            order_data = json.loads(order.data)
            if 'aliexpress' not in order_data:
                order_data['aliexpress'] = {}
        except:
            order_data = {'aliexpress': {}}

        order_data['aliexpress']['end_reason'] = data.get('end_reason')

        try:
            order_data['aliexpress']['order_details'] = json.loads(data.get('order_details'))
        except:
            pass

        order.data = json.dumps(order_data)

        order.save()

        # Send e-mail notifications for cancelled orders
        cancelled_order_alert.send_email()

        # process fulfilment fee
        process_sale_transaction_fee(order)

        return self.api_success()
