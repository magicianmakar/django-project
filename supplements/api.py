import base64
import json
from io import BytesIO
from decimal import Decimal

from django.conf import settings
from django.utils.crypto import get_random_string
from django.views.generic import View

from pdfrw import PdfWriter
from raven.contrib.django.raven_compat.models import client as raven_client

from leadgalaxy.utils import aws_s3_upload
from shopified_core.mixins import ApiResponseMixin
from shopified_core.utils import get_store_api
from shopified_core import permissions

from .lib.image import data_url_to_pil_image, get_mockup, get_order_number_label, pil_to_fp
from .lib.shipstation import create_shipstation_order, prepare_shipstation_data
from .models import Payout, PLSOrder
from .utils.payment import Util, get_shipping_cost
from django.utils.text import slugify


class SupplementsApi(ApiResponseMixin, View):
    http_method_names = ['get', 'post', 'delete']

    def post_make_payment(self, request, user, data):
        util = Util()
        store = util.get_store(data['store_id'], data['store_type'])
        permissions.user_can_view(user, store)

        util.store = store

        success = error = invalid_country = inventory_error = 0
        success_ids = []

        info = util.prepare_data(data['order_data_ids'])
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
                raven_client.captureException(level='warning')
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
                            'aliexpress_order_id': str(pls_order.stripe_transaction_id),
                            'source_type': 'supplements'
                        }

                        api_result = StoreApi.post_order_fulfill(request, user, data)
                        if api_result.status_code != 200:
                            error += 1
                            raven_client.captureMessage('Unable to track supplement', extra={
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
        try:
            payout = Payout.objects.get(reference_number=reference_number)
        except Payout.DoesNotExist:
            return self.api_error('Payout not found', status=404)

        order.payout = payout
        order.save()

        return self.api_success()

    def post_ajaxify_label(self, request, user, data):
        image_data = data['image_data_url']
        mockup_type = data['mockup_slug']
        label_image = data_url_to_pil_image(image_data)
        bottle_mockup = get_mockup(label_image, mockup_type)
        image_fp = pil_to_fp(bottle_mockup)
        image_fp.seek(0)
        image_fp.name = 'mockup.png'

        img_data = image_fp.getvalue()
        data = base64.b64encode(img_data)
        image_data = data.decode()
        data_url = f'data:image/jpeg;base64,{image_data}'

        return self.api_success({'data_url': data_url})

    def post_calculate_shipping_cost(self, request, user, data):
        shipping_price = get_shipping_cost(data['country-code'], data.get('province-code'), data['total-weight'])
        data = {'shipping_cost': shipping_price}
        if shipping_price is False:
            return self.api_error('Shipping cost not available', status=404)
        else:
            return self.api_success(data)

    def post_sync_order(self, request, user, data):
        try:
            print(data.get('source_id'))
            order = PLSOrder.objects.get(
                stripe_transaction_id=data.get('source_id'),
                user=request.user.models_user
            )
        except PLSOrder.DoesNotExist:
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
                'source_id': order.stripe_transaction_id,
            }
        })
