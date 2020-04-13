import base64
from io import BytesIO

from django.conf import settings
from django.utils.crypto import get_random_string
from django.views.generic import View

from pdfrw import PdfWriter
from raven.contrib.django.raven_compat.models import client as raven_client

from leadgalaxy.utils import aws_s3_upload
from shopified_core.mixins import ApiResponseMixin

from .lib.image import data_url_to_pil_image, get_mockup, get_order_number_label, pil_to_fp
from .lib.shipstation import create_shipstation_order, prepare_shipstation_data
from .models import Payout, PLSOrder
from .utils.payment import Util, get_shipping_cost


class SupplementsApi(ApiResponseMixin, View):
    http_method_names = ['get', 'post', 'delete']

    def post_make_payment(self, request, user, data):
        util = Util()
        store = util.get_store(data['store_id'], data['store_type'])
        util.store = store

        success = error = invalid_country = 0
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
            target_countries = []
            for line in order_line_items:
                user_supplement = line['user_supplement']
                shipping_countries = user_supplement.shipping_countries
                target_countries.extend(shipping_countries)

            target_countries = set(target_countries)
            if target_countries and shipping_country not in set(target_countries):
                invalid_country += 1
                continue

            try:
                pls_order = util.make_payment(
                    order_info,
                    order_line_items,
                    user,
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
