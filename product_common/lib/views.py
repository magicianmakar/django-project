import mimetypes
import simplejson as json
from decimal import Decimal
from urllib.parse import parse_qs, urlparse

from django.conf import settings
from django.shortcuts import reverse
from django.utils.crypto import get_random_string

from leadgalaxy.utils import aws_s3_upload


def upload_object_to_aws(path, name, fp):
    ext = name.rsplit('.')[-1]
    # Randomize filename in order to not overwrite an existing file
    random_name = get_random_string(length=10)

    object_name = f'{path}/{random_name}.{ext}'
    mimetype = mimetypes.guess_type(name)[0]

    return aws_s3_upload(
        filename=object_name,
        fp=fp,
        mimetype=mimetype,
        bucket_name=settings.S3_UPLOADS_BUCKET
    )


def upload_image_to_aws(image, bucket_name, user_id):
    path = f'uploads/u{user_id}/{bucket_name}'
    return upload_object_to_aws(path, image.name, image)


class BaseMixin:
    model = None
    namespace = 'market'

    def get_template(self):
        raise NotImplementedError


class SendToStoreMixin:
    def get_store_data(self, user):
        shopify_stores = user.profile.get_shopify_stores()
        chq_stores = user.profile.get_chq_stores()
        gkart_stores = user.profile.get_gkart_stores()
        woo_stores = user.profile.get_woo_stores()
        big_stores = user.profile.get_bigcommerce_stores()
        ebay_stores = user.profile.get_ebay_stores(do_sync=True)
        fb_stores = user.profile.get_fb_stores()
        google_stores = user.profile.get_google_stores()

        store_data = dict(
            shopify=[{'id': s.id, 'value': s.title} for s in shopify_stores],
            chq=[{'id': s.id, 'value': s.title} for s in chq_stores],
            gkart=[{'id': s.id, 'value': s.title} for s in gkart_stores],
            woo=[{'id': s.id, 'value': s.title} for s in woo_stores],
            ebay=[{'id': s.id, 'value': s.title} for s in ebay_stores],
            fb=[{'id': s.id, 'value': s.title} for s in fb_stores],
            google=[{'id': s.id, 'value': s.title} for s in google_stores],
            bigcommerce=[{'id': s.id, 'value': s.title} for s in big_stores],
        )

        store_types = []
        if store_data['shopify']:
            store_types.append(('shopify', 'Shopify'))

        if store_data['chq']:
            store_types.append(('chq', 'CommerceHQ'))

        if store_data['gkart']:
            store_types.append(('gkart', 'GrooveKart'))

        if store_data['woo']:
            store_types.append(('woo', 'WooCommerce'))

        if store_data['ebay']:
            store_types.append(('ebay', 'eBay'))

        if store_data['fb']:
            store_types.append(('fb', 'Facebook'))

        if store_data['google']:
            store_types.append(('google', 'Google'))

        if store_data['bigcommerce']:
            store_types.append(('bigcommerce', 'BigCommerce'))

        return dict(store_data=store_data, store_types=store_types)

    def get_api_data(self, product):
        data = product.to_dict()

        product_id = product.id
        kwargs = {'product_id': product_id}
        url_name = f'{self.namespace}:product_detail'
        original_url = reverse(url_name, kwargs=kwargs)
        data['original_url'] = self.request.build_absolute_uri(original_url)

        api_data = {}
        api_data = self.serialize_api_data(data)

        return api_data

    def serialize_api_data(self, data):
        cost_price = data['cost_price']
        price = Decimal(1.3) * cost_price
        compare_at_price = Decimal(1.5) * cost_price

        return json.dumps(dict(
            title=data['title'],
            description=data['description'],
            type=data['category'],
            vendor="Dropified",
            weight=0,  # TODO: Confirm
            weight_unit="lbs",  # TODO: Confirm
            tags=data['tags'],
            variants=[],
            images=data['image_urls'],
            price=price,
            cost_price=data['cost_price'],
            compare_at_price=compare_at_price,
            original_url=data['original_url'],
            product_id=data['product_id'],
            sku=data['shipstation_sku'],
            store=dict(
                name="Dropified",
                url='',
            ),
        ), use_decimal=True)


class PagingMixin:

    def add_paging_context(self, context):
        paginator = context['paginator']
        page = context['page_obj']
        page_range = paginator.page_range

        full_path = self.request.get_full_path()

        path_info = urlparse(full_path)
        query = path_info.query

        query_data = parse_qs(query)
        if 'page' in query_data:
            query_data.pop('page')

        query_string = "&".join(
            f"{k}={','.join(v)}" for k, v in query_data.items()
        )

        path = path_info.path
        if query_string:
            paging_path = f"{path}?{query_string}&"
        else:
            paging_path = f"{path}?"

        context['paging_path'] = paging_path

        # Window management
        page_range = paginator.page_range
        current_index = page.number - 1  # Zero based index
        num_pages = paginator.num_pages

        window_length = 5

        if num_pages <= window_length:
            context['page_range'] = page_range
            return

        lr_width = window_length // 2
        left_index = current_index - lr_width
        right_index = current_index + lr_width

        if left_index < 0:
            left_index = 0
            right_index = window_length - 1

        if right_index >= num_pages:
            left_index = num_pages - window_length
            right_index = num_pages - 1

        context['page_range'] = page_range[left_index:right_index + 1]
