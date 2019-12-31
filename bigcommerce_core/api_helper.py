from django.core.urlresolvers import reverse

from shopified_core.api_helper import ApiHelperBase
from shopified_core.utils import order_data_cache_key
from . import tasks
from . import utils


class BigCommerceApiHelper(ApiHelperBase):
    def smart_board_sync(self, user, board):
        pass

    def format_order_key(self, order_key):
        order_key = order_data_cache_key(order_key, prefix='bigcommerce_order')

        store_type, prefix, store, order, line = order_key.split('_')
        return order_key, store

    def create_image_zip(self, images, product):
        tasks.create_image_zip.delay(images, product.id)

    def set_order_note(self, store, order_id, note):
        if note == utils.get_latest_order_note(store, order_id):
            return True

        return utils.add_bigcommerce_order_note(store, order_id, note)

    def get_product_path(self, pk):
        return reverse('bigcommerce:product_detail', args=[pk])

    def after_post_product_connect(self, product, source_id):
        product.save()
        product.sync()

    def duplicate_product(self, product):
        return utils.duplicate_product(product)

    def split_product(self, product, split_factor, user):
        splitted_products = utils.split_product(product, split_factor)
        return [p.id for p in splitted_products]

    def product_save(self, data, user_id, target, request):
        return tasks.product_save(data, user_id)

    def set_product_default_supplier(self, product, supplier):
        return supplier

    def sync_product_quantities(self, product_id):
        tasks.sync_bigcommerce_product_quantities.apply_async(args=[product_id], expires=600)
