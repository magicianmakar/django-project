from django.urls import reverse

from shopified_core.api_helper import ApiHelperBase
from shopified_core.utils import order_data_cache_key

from . import tasks
from . import utils
from product_alerts.models import ProductChange


class GrooveKartApiHelper(ApiHelperBase):
    def smart_board_sync(self, user, board):
        pass

    def after_delete_product_connect(self, product, source_id):
        utils.map_variants(product, product.parsed)
        product.save()

    def format_order_key(self, order_key):
        order_key = order_data_cache_key(order_key, prefix='gkart_order')

        store_type, prefix, store, order, line = order_key.split('_')
        return order_key, store

    def get_user_stores_for_type(self, user, **kwargs):
        return user.profile.get_gkart_stores(**kwargs)

    def create_image_zip(self, images, product):
        tasks.create_image_zip.delay(images, product.id)

    def set_order_note(self, store, order_id, note):
        return utils.set_gkart_order_note(store, order_id, note)

    def get_product_path(self, pk):
        return reverse('gkart:product_detail', args=[pk])

    def after_post_product_connect(self, product, source_id):
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

    def filter_productchange_by_store(self, store):
        return ProductChange.objects.filter(gkart_product__store=store)
