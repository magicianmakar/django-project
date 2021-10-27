from django.conf import settings
from django.utils.crypto import get_random_string

from shopified_core.api_helper import ApiHelperBase
from shopified_core.utils import order_data_cache_key

from . import tasks


class EbayApiHelper(ApiHelperBase):
    def format_order_key(self, order_key):
        order_key = order_data_cache_key(order_key, prefix='ebay_order')

        store_type, prefix, store, order, line = order_key.split('_')
        return order_key, store

    def product_save(self, data, user_id, target, request):
        pusher_channel = f"import_ebay_product_{get_random_string(32, 'abcdef0123456789')}"
        tasks.product_save.apply_async(kwargs={
            'req_data': data,
            'user_id': user_id,
            'pusher_channel': pusher_channel
        })
        return {
            'product': {
                'pusher': {'key': settings.PUSHER_KEY, 'channel': pusher_channel}
            }
        }

    def set_product_default_supplier(self, product, supplier):
        return supplier
