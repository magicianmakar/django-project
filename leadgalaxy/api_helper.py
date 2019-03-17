from django.core.cache import cache

from shopified_core.api_helper import ApiHelperBase
from . import tasks


class ShopifyApiHelper(ApiHelperBase):
    def smart_board_sync(self, user, board):
        pass

    def after_delete_product_connect(self, product, source_id):
        cache.delete('export_product_{}_{}'.format(product.store.id, source_id))
        tasks.update_product_connection.delay(product.store.id, source_id)
