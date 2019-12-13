import simplejson as json

from django.core.cache import cache
from django.core.urlresolvers import reverse

from shopified_core.api_helper import ApiHelperBase
from shopified_core.utils import hash_url_filename, order_data_cache_key
from .models import ProductSupplier
from . import tasks
from . import utils
from product_alerts.models import ProductChange


class ShopifyApiHelper(ApiHelperBase):
    def smart_board_sync(self, user, board):
        pass

    def after_delete_product_connect(self, product, source_id):
        cache.delete('export_product_{}_{}'.format(product.store.id, source_id))
        tasks.update_product_connection.delay(product.store.id, source_id)

    def format_order_key(self, order_key):
        order_key = order_data_cache_key(order_key, prefix='order')

        prefix, store, order, line = order_key.split('_')
        return order_key, store

    def get_user_stores_for_type(self, user, **kwargs):
        return user.profile.get_shopify_stores(**kwargs)

    def get_unfulfilled_order_tracks(self, order_tracks):
        return order_tracks.filter(source_tracking='') \
                           .filter(shopify_status='') \
                           .exclude(source_status='FINISH')

    def create_image_zip(self, images, product):
        tasks.create_image_zip.apply_async(args=[images, product.id], countdown=5)

    def set_order_note(self, store, order_id, note):
        return utils.set_shopify_order_note(store, order_id, note)

    def get_product_path(self, pk):
        return reverse('product_view', args=[pk])

    def after_post_product_connect(self, product, source_id):
        product.save()

        cache.delete('export_product_{}_{}'.format(product.store.id, source_id))
        tasks.update_product_connection.delay(product.store.id, source_id)

        tasks.update_shopify_product(product.store.id, source_id, product_id=product.id)

    def get_connected_products(self, product_model, store, source_id):
        return product_model.objects.filter(
            store=store,
            shopify_id=source_id
        )

    def duplicate_product(self, product):
        return utils.duplicate_product(product)

    def split_product(self, product, split_factor, user):
        splitted_products, active_variant_idx = utils.split_product(product, split_factor)

        # if current product is connected, automatically connect splitted products.
        if product.shopify_id:
            shopify_product = utils.get_shopify_product(product.store, product.shopify_id)
            shopify_variants = shopify_product['variants']
            for option_value, splitted_product in list(splitted_products.items()):
                data = json.loads(splitted_product.data)

                variants = []
                for v in shopify_variants:
                    if v.get('option{}'.format(active_variant_idx), None) == option_value:
                        v.pop('id', None)
                        v.pop('image_id', None)

                        # shift options
                        option_idx = active_variant_idx
                        while v.get('option{}'.format(option_idx + 1), None):
                            v['option{}'.format(option_idx)] = v['option{}'.format(option_idx + 1)]
                            option_idx += 1
                        v.pop('option{}'.format(option_idx), None)

                        variants.append(v)

                images = []
                for i in data['images']:
                    img = {'src': i}
                    img_filename = hash_url_filename(i)
                    if data['variants_images'] and img_filename in data['variants_images']:
                        img['filename'] = 'v-{}__{}'.format(data['variants_images'][img_filename], img_filename)

                    images.append(img)

                req_data = {
                    'product': splitted_product.id,
                    'store': splitted_product.store_id,
                    'data': json.dumps({
                        'product': {
                            'title': data['title'],
                            'body_html': data['description'],
                            'product_type': data['type'],
                            'vendor': data['vendor'],
                            'published': data['published'],
                            'tags': data['tags'],
                            'variants': variants,
                            'options': [{'name': v['title'], 'values': v['values']} for v in data['variants']],
                            'images': images
                        }
                    })
                }

                tasks.export_product.apply_async(args=[req_data, 'shopify', user.id], expires=60)

        return [p.id for v, p in splitted_products.items()]

    def set_product_default_supplier(self, product, supplier):
        if not product.default_supplier:
            supplier = product.get_supplier_info()
            product.default_supplier = ProductSupplier.objects.create(
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
        return ProductChange.objects.filter(shopify_product__store=store)

    def sync_product_quantities(self, product_id):
        tasks.sync_shopify_product_quantities.apply_async(args=[product_id], expires=600)
