from django.core.urlresolvers import reverse

from shopified_core.api_helper import ApiHelperBase
from shopified_core.utils import order_data_cache_key
from .models import CommerceHQSupplier
from . import tasks
from . import utils
from product_alerts.models import ProductChange


class CHQApiHelper(ApiHelperBase):
    def smart_board_sync(self, user, board):
        pass

    def after_delete_product_connect(self, product, source_id):
        options = product.parsed.get('options', [])
        new_options = [{'values': i['values'], 'title': i['title']} for i in options]
        if new_options:
            product.update_data({'variants': new_options})
            product.save()

    def format_order_key(self, order_key):
        order_key = order_data_cache_key(order_key, prefix='order')

        prefix, store, order, line = order_key.split('_')
        return order_key, store

    def get_user_stores_for_type(self, user, **kwargs):
        return user.profile.get_chq_stores(**kwargs)

    def create_image_zip(self, images, product):
        tasks.create_image_zip.apply_async(args=[images, product.id], countdown=5)

    def set_order_note(self, store, order_id, note):
        return utils.set_chq_order_note(store, order_id, note)

    def get_product_path(self, pk):
        return reverse('chq:product_detail', args=[pk])

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
        if not product.default_supplier:
            supplier = product.get_supplier_info()
            product.default_supplier = CommerceHQSupplier.objects.create(
                store=product.store,
                product=product,
                product_url=product.get_original_info().get('url', ''),
                supplier_name=supplier.get('name') if supplier else '',
                supplier_url=supplier.get('url') if supplier else '',
                is_default=True
            )

            return product.default_supplier

        return supplier

    def filter_productchange_by_store(self, store):
        return ProductChange.objects.filter(chq_product__store=store)

    def get_store_tracking_carriers(self, store):
        return utils.store_shipping_carriers(store)
