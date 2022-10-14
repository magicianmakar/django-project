from django.conf import settings
from django.contrib.auth.models import User
from django.db.models import Q
from django.urls import reverse
from django.utils.crypto import get_random_string

from shopified_core import permissions
from shopified_core.api_helper import ApiHelperBase
from shopified_core.utils import order_data_cache_key, safe_json
from suredone_core.utils import SureDonePusher

from . import tasks
from .models import EbayProduct
from .utils import EbayUtils


class EbayApiHelper(ApiHelperBase):
    def smart_board_sync(self, user, board):
        permissions.user_can_edit(user, board)
        board.products.clear()
        config = safe_json(board.config)
        query_filter = Q()

        def format_query_filter(source_key, target_key=None):
            nonlocal query_filter, config
            if target_key is None:
                target_key = source_key
            keys = [k.strip() for k in config.get(source_key, '').split(',')]
            for k in keys:
                query_filter &= Q(**{f'{target_key}__icontains': k})

        if config.get('title'):
            format_query_filter('title')
        if config.get('tags'):
            format_query_filter('tags')
        if config.get('type'):
            format_query_filter('type', 'product_type')

        products = EbayProduct.objects.filter(query_filter, user=user.models_user)
        for product in products:
            permissions.user_can_edit(user, product)
        if products.count() > 0:
            board.products.add(*products)

    def format_order_key(self, order_key):
        order_key = order_data_cache_key(order_key, prefix='ebay_order')

        store_type, prefix, store, order, line = order_key.split('_')
        return order_key, store

    def product_save(self, data, user_id, target, request):
        user = User.objects.filter(id=user_id).first()
        pusher_channel = f"import_ebay_product_{get_random_string(32, 'abcdef0123456789')}"
        sd_pusher = SureDonePusher(pusher_channel)
        default_event = 'ebay-product-save'
        create_product_limit_check, product_limit_check, logs_count = EbayUtils(user).check_product_create_limit(
            sd_pusher, default_event)

        if create_product_limit_check == 'Limit Reached':
            return {
                'product': {
                    'pusher': {'key': settings.PUSHER_KEY, 'channel': pusher_channel},
                    'error': f'Your current plan allows up to {product_limit_check} created product(s). Currently you '
                             f'have {logs_count} created products.'
                }
            }

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

    def split_product(self, product, split_factor, user):
        """
        Split an existing product on SureDone and push all changes to Dropified DB
        :param product: product for split
        :type product: EbayProduct
        :param split_factor:
        :type split_factor: str
        :param user:
        :type user:
        :return: SureDone's API response
        :rtype: JsonResponse
        """

        tasks.product_split.apply_async(kwargs={
            'product_guid': product.guid,
            'split_factor': split_factor,
            'user_id': user.id,
        }, countdown=0, expires=240)

        pusher = {'key': settings.PUSHER_KEY, 'channel': product.store.pusher_channel()}
        return {'pusher': pusher}

    def get_product_path(self, data):
        """
        Returns a path for product detail view
        Args:
            data:
                store_id: store ID which owns the product
                guid: GUID of the product
        """
        return reverse('ebay:product_detail', args=[data['store_id'], data['guid']])
