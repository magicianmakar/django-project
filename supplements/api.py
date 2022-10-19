import arrow
import json
from decimal import Decimal
from io import BytesIO

from django.conf import settings
from django.contrib.auth.models import User
from django.db.models import Q
from django.db.transaction import atomic
from django.urls import reverse
from django.utils.crypto import get_random_string
from django.views.generic import View
from django.utils import timezone

from pdfrw import PdfWriter

from leadgalaxy.utils import aws_s3_upload
from lib.exceptions import capture_exception
from product_common.models import ProductSupplier
from shopified_core import permissions
from shopified_core.mixins import ApiResponseMixin

from .lib.image import get_order_number_label
from .lib.shipstation import create_shipstation_order, send_shipstation_orders
from .models import Payout, PLSOrder, PLSOrderLine, UserSupplement, UserSupplementLabel, BasketItem, PLSupplement, AuthorizeNetCustomer
from .utils import user_can_download_label
from .utils.payment import Util, get_shipping, get_shipping_costs
from .utils.basket import BasketStore
from shopified_core.utils import (
    safe_int,
    safe_float,
    clean_tracking_number,
    CancelledOrderAlert
)
from shopified_core.shipping_helper import province_code_from_name, country_from_code
from my_basket.models import BasketOrderTrack
from fulfilment_fee.utils import process_sale_transaction_fee
from basicauth.decorators import basic_auth_required
from django.utils.decorators import method_decorator
from supplements.lib.authorizenet import create_customer_profile


class SupplementsApi(ApiResponseMixin, View):
    http_method_names = ['get', 'post', 'delete']

    def post_process_orders(self, request, user, data):
        if not user.models_user.can('pls.use'):
            return self.api_error('Your current plan doesn\'t have this feature.', status=403)

        if not user.can('place_private_label_orders.sub'):
            return self.api_error('Subuser not allowed to place private label orders', status=403)

        util = Util()
        store = util.get_store(data['store_id'], data['store_type'])
        permissions.user_can_view(user, store)

        orders, orders_status, order_costs = util.get_order_data(
            request.user,
            list(set(data['order_data_ids'])),
            data.get('shippings', {}),
            data.get('pay_taxes', {})
        )

        if not orders or data.get('validate'):
            return self.api_success({
                'orders_status': list(orders_status.values()),
                'shippings': order_costs['shipping'],
                'taxes': order_costs['taxes'],
            })

        total_amount = 0
        order = list(orders.values())[0]
        country = order.get('shipping_address').get('country')
        country_code = order.get('shipping_address').get('country_code')

        for item in order['items']:
            total_amount += item['quantity'] * item['user_supplement'].pl_supplement.cost_price

        total_amount = Decimal(total_amount)
        total_amount += order["selected_shipping"]["shipping_cost"]

        if (country == 'United Kingdom' or country_code == 'GB') \
                and total_amount < Decimal('180'):
            error = ''
            if not user.profile.company:
                error = f'Please add your company information in Profile settings \
                        <a target="_blank" href="{reverse("user_profile")}"> <u>here.</u></a>'
            elif not user.profile.company.vat:
                error = f'Please add VAT number under company information in Profile settings \
                        <a target="_blank" href="{reverse("user_profile")}"> <u>here.</u></a>'

            if error:
                return self.api_error(error, status=500)

        paid_orders = []
        try:
            with atomic():
                for order_id in orders_status:
                    if orders_status[order_id]['success']:
                        orders_status[order_id]['status'] = 'Processing payment'

                unpaid_orders = []
                for order in orders.values():
                    if not order.get('items'):
                        continue

                    order_shippings = order_costs['shipping'].get(order['id'])
                    if not order_shippings or order_shippings[0].get('error'):
                        continue

                    unpaid_order = util.create_unpaid_order(
                        order,
                        user.models_user,
                        order_shippings
                    )
                    unpaid_orders.append(unpaid_order)

                paid_orders = util.create_payment(user.models_user, unpaid_orders)
        except Exception as e:
            error_code = str(e).split(':')
            if error_code[0] == "User has no authorize_net_customer.":
                error_msg = f'Please enter your billing information in the Private Label > Billing tab \
                            <a target="_blank" href="{reverse("pls:billing")}"> <u>here.</u></a>'
            else:
                error_code_lookup = f'https://developer.authorize.net/api/reference/responseCodes.html?code={error_code[0]}'
                capture_exception(level='warning')
                error_msg = f'Payment failed with Error Code {str(e)} <a target="_blank" href="{error_code_lookup}"> Learn more.</a>'
            return self.api_error(error_msg, status=500)

        send_shipstation_orders()
        for pls_order in paid_orders:
            item_track_map = {}
            for item in pls_order.order_items.all():
                if item_track_map.get(item.line_id):  # Bundled items
                    item.order_track_id = item_track_map[item.line_id]

                item.save_order_track()

                order_data_id = f'{store.id}_{item.store_order_id}_{item.line_id}'
                if item.order_track_id:
                    item_track_map[item.line_id] = item.order_track_id
                    orders_status[order_data_id].update({
                        'success': True,
                        'placed': True,
                        'status': 'Order placed'
                    })

                else:
                    orders_status[order_data_id].update({
                        'success': False,
                        'status': 'Order placed but unable to automatically track, please contact support.'
                                  + f' (Dropified Order ID: {pls_order.get_dropified_source_id()})'
                    })

        return self.api_success({
            'orders_status': list(orders_status.values()),
            'shippings': order_costs['shipping'],
            'taxes': order_costs['taxes'],
        })

    def post_order_taxes(self, request, user, data):
        util = Util()
        store = util.get_store(data['store_id'], data['store_type'])
        permissions.user_can_view(user, store)

        orders, orders_status, order_costs = util.get_order_data(
            request.user,
            data['order_data_ids'],
            data['shippings'],
            data['pay_taxes']
        )

        for order_id in orders:
            order_costs['taxes'][order_id] = util.calculate_taxes(orders[order_id])
            order_costs['taxes'][order_id]['pay_taxes'] = orders[order_id].get('pay_taxes', False)

        return self.api_success({
            'orders_status': list(orders_status.values()),
            'shippings': order_costs['shipping'],
            'taxes': order_costs['taxes'],
        })

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

    def post_sync_order(self, request, user, data):
        order = PLSOrder.objects.filter(
            Q(stripe_transaction_id=data.get('source_id'))
            | Q(id=data.get('source_id')),
            user=request.user.models_user
        ).first()

        if order is None:
            return self.api_error('Order not found', status=404)

        order_item = order.order_items.filter(order_track_id=data['track_id']).first()
        if not order_item:
            [i.save_order_track() for i in order.order_items.all()]
        else:
            order_item.save_order_track()

        order_items = order.order_items.filter(order_track_id=data['track_id'])
        return self.api_success({'orders': [{
            "source": {
                'id': order.id,
                'status': order.source_status,
                'orderStatus': order.source_status,
                'tracking_number': order.tracking_numbers_str,
                'order_details': order.payment_details,
                'source_id': order.get_dropified_source_id(),
                'source_url': order.source_url
            }
        } for order_item in order_items]})

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
        latest_label_url = label_url

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
                user.models_user.authorize_net_customer
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
            line_total=(i.amount * i.quantity) / 100.,
            line_total_string="${:.2f}".format((i.amount * i.quantity) / 100.)
        ) for i in order.order_items.all()]

        try:
            customer_id = request.user.authorize_net_customer.customer_id
        except AuthorizeNetCustomer.DoesNotExist:
            customer_id = create_customer_profile(request.user)
            auth_net_user = AuthorizeNetCustomer(
                user=request.user,
            )
            auth_net_user.customer_id = customer_id
            auth_net_user.save()

        transaction_status = request.user.authorize_net_customer.status(order.stripe_transaction_id)

        return self.api_success({
            'items': line_items,
            'transaction_status': str(transaction_status),
            'shipping_price': order.shipping_price / 100.,
            'shipping_price_string': order.shipping_price_string,
            'amount': order.amount / 100.
        })

    def post_create_payouts(self, request, user, data):
        if not request.user.can('pls_admin.use'):
            raise permissions.PermissionDenied()

        lines_count = 0
        supplier_ids = data.keys()
        for id in supplier_ids:
            supplier = ProductSupplier.objects.get(id=id)
            try:
                date = data[id].get('date').split('-')
                start_date = arrow.get(date[0], 'M/D/YYYY').datetime
                end_date = arrow.get(f'{date[1]} 235959', 'M/D/YYYY Hms').datetime
            except Exception:
                start_date, end_date = None, None

            if supplier.is_shipping_supplier:
                if start_date and end_date:
                    line_items = PLSOrderLine.objects.filter(pls_order__is_fulfilled=True,
                                                             shipping_payout__isnull=True,
                                                             created_at__gte=start_date,
                                                             created_at__lte=end_date)
                else:
                    line_items = PLSOrderLine.objects.filter(pls_order__is_fulfilled=True,
                                                             shipping_payout__isnull=True)

                if line_items.count():
                    payout = Payout.objects.create(reference_number=data[id].get('ref_num'),
                                                   supplier=supplier,
                                                   start_date=start_date,
                                                   end_date=end_date)
                    lines_count += line_items.count()

                    line_items.update(shipping_payout=payout)
            else:
                if start_date and end_date:
                    line_items = PLSOrderLine.objects.filter(pls_order__is_fulfilled=True,
                                                             label__user_supplement__pl_supplement__supplier=supplier,
                                                             line_payout__isnull=True,
                                                             created_at__gte=start_date,
                                                             created_at__lte=end_date)
                else:
                    line_items = PLSOrderLine.objects.filter(pls_order__is_fulfilled=True,
                                                             label__user_supplement__pl_supplement__supplier=supplier,
                                                             line_payout__isnull=True)
                if line_items.count():
                    payout = Payout.objects.create(reference_number=data[id].get('ref_num'),
                                                   supplier=supplier,
                                                   start_date=start_date,
                                                   end_date=end_date)

                    lines_count += line_items.count()

                    line_items.update(line_payout=payout)

        return self.api_success({'count': lines_count})

    def post_add_basket(self, request, user, data):
        product_id = data['product-id']

        try:
            user_supplement = user.pl_supplements.get(id=product_id)
        except UserSupplement.DoesNotExist:
            return self.api_error('Product not found', status=404)

        if user_supplement.current_label:
            if user_supplement.current_label.status != "approved":
                return self.api_error('Label not approved yet', status=500)
        else:
            if not user_supplement.pl_supplement.approved_label_url:
                return self.api_error('No Sample label for this product', status=500)
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
        total_weight = []
        for basket_item in basket_items:
            total_weight.append(basket_item.user_supplement.pl_supplement.weight * basket_item.quantity)

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

    def copy_billing_address(self, data):
        data = data.copy()
        data['shipping_first_name'] = data['billing_first_name']
        data['shipping_last_name'] = data['billing_last_name']
        data['shipping_country'] = data['billing_country']
        data['shipping_company_name'] = data['billing_company_name']
        data['shipping_phone'] = data['billing_phone']
        data['shipping_address_line1'] = data['billing_address_line1']
        data['shipping_address_line2'] = data['billing_address_line2']
        data['shipping_city'] = data['billing_city']
        data['shipping_state'] = data['billing_state']
        data['shipping_zip_code'] = data['billing_zip_code']
        data['shipping_email'] = data['billing_email']
        return data

    def post_basket_make_payment(self, request, user, data):
        if data['shipping_address'] == 'true':
            data = self.copy_billing_address(data)

        country_code = data['shipping_country']
        province = data['shipping_state']
        billing_country_code = data['billing_country']
        billing_province = data['billing_state']
        shipping_service = data['shipping_service']

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
        try:
            shipping_country = shipping_country.split(',')[0]
        except Exception:
            pass

        total_weight = []
        order_line_items = []
        pl_supplement_inventory = {}
        basket_items = user.basket_items.select_related('user_supplement__pl_supplement').all()
        for basket_item in basket_items:
            # Multiple items with different labels but same base product can be ordered
            pl_supplement_id = basket_item.user_supplement.pl_supplement_id
            quantity_left = pl_supplement_inventory.get(pl_supplement_id)
            if quantity_left is None:
                pl_supplement_inventory[pl_supplement_id] = basket_item.user_supplement.pl_supplement.inventory
                quantity_left = pl_supplement_inventory[pl_supplement_id]

            if basket_item.quantity > quantity_left:
                return self.api_error(f"{basket_item.user_supplement.title} doesn't have enough stock ({quantity_left} left)",
                                      status=500)
            pl_supplement_inventory[pl_supplement_id] -= basket_item.quantity

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

            if basket_item.user_supplement.current_label is None:
                new_label = basket_item.user_supplement.labels.create(url=basket_item.user_supplement.pl_supplement.approved_label_url,
                                                                      status=UserSupplementLabel.APPROVED)
                basket_item.user_supplement.current_label = new_label
                basket_item.user_supplement.current_label.generate_sku()
                basket_item.user_supplement.current_label.save()
                basket_item.user_supplement.save()

            order_line['label'] = basket_item.user_supplement.current_label
            order_line['title'] = basket_item.user_supplement.title
            order_line['sku'] = basket_item.user_supplement.pl_supplement.shipstation_sku

            total_weight.append(basket_item.user_supplement.pl_supplement.weight * basket_item.quantity)
            order_line_items.append(order_line)

        util = Util()
        util.store = BasketStore()
        checkout_data['line_items'] = order_line_items
        basket_order = util.store.create_order(user, checkout_data)
        order_info = (basket_order.id, basket_order.id, country_code,
                      province_code, shipping_service)
        order = basket_order.get_order()

        shipping = get_shipping(
            country_code,
            province_code,
            total_weight,
            shipping_service,
        )
        total_amount = 0
        country = order.get('shipping_address').get('country')
        country_code = order.get('shipping_address').get('country_code')

        for item in order['line_items']:
            total_amount += item['quantity'] * item['price']

        total_amount = Decimal(total_amount)
        total_amount += Decimal(shipping['shipping_cost'])

        if (country == 'United Kingdom' or country_code == 'GB') \
                and total_amount < Decimal('180'):
            error = ''
            if not user.profile.company:
                error = f'Please add your company information in Profile settings \
                        <a target="_blank" href="{reverse("user_profile")}"> <u>here.</u></a>'
            elif not user.profile.company.vat:
                error = f'Please add VAT number under company information in Profile settings \
                        <a target="_blank" href="{reverse("user_profile")}"> <u>here.</u></a>'
            if error:
                return self.api_error(error, status=500)

        try:
            pls_order = util.make_payment(
                order_info,
                order_line_items,
                user.models_user,
                order,
            )
        except Exception as e:
            basket_order.delete()
            error_code = str(e).split(':')
            if error_code[0] == "User has no authorize_net_customer.":
                error_msg = f'Please enter your billing information in the Private Label > Billing tab \
                            <a target="_blank" href="{reverse("pls:billing")}"> <u>here.</u></a>'
            else:
                error_code_lookup = f'https://developer.authorize.net/api/reference/responseCodes.html?code={error_code[0]}'
                capture_exception(level='warning')
                error_msg = f'Payment failed with Error Code {str(e)} <a target="_blank" href="{error_code_lookup}"> Learn more.</a>'
            return self.api_error(error_msg, status=500)
        else:
            # clear basket items
            user.basket_items.all().delete()
            orderlines = PLSOrderLine.objects.filter(pls_order=pls_order.id)
            for order_line in orderlines:
                shipstation_acc = order_line.label.user_supplement.pl_supplement.shipstation_account
                create_shipstation_order(pls_order, shipstation_acc)
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


# PLOD public api (Inventory sync)
class SupplementsPublicApi(ApiResponseMixin, View):
    http_method_names = ['get', 'post']
    login_non_required = ['inventory', 'decrease_inventory']

    @method_decorator(basic_auth_required)
    def get_inventory(self, request, user, data):
        sku = data.get('shipstation_sku', False)

        # getting PLSupplement by sku
        try:
            pl_supplement = PLSupplement.objects.get(shipstation_sku=sku)
            return self.api_success({
                'somevar': "okok",
                "sku": sku,
                "pl_supplement": pl_supplement.to_dict(),
                "inventory": pl_supplement.inventory
            })
        except PLSupplement.DoesNotExist:
            return self.api_error('SKU Not Found', status=404)

    @method_decorator(basic_auth_required)
    def post_decrease_inventory(self, request, user, data):
        sku = data.get('shipstation_sku', False)
        inventory = data.get('inventory', False)

        # getting PLSupplement by sku
        try:
            pl_supplement = PLSupplement.objects.get(shipstation_sku=sku)
            if inventory:
                new_inventory = safe_int(pl_supplement.inventory) - safe_int(inventory)
                if new_inventory < 0:
                    return self.api_error('Not enough inventory', status=500)
                pl_supplement.inventory = new_inventory
                pl_supplement.save()
            return self.api_success({
                "sku": sku,
                "pl_supplement": pl_supplement.to_dict(),
                "inventory": pl_supplement.inventory
            })
        except PLSupplement.DoesNotExist:
            return self.api_error('SKU Not Found', status=404)

    # disable user Auth, use api Basic AUTH settings instead
    def get_user(self, request, data=None, assert_login=True):
        return None
