import itertools
import json

from django.conf import settings

from bigcommerce_core.utils import get_image_url_by_hash
from leadgalaxy.utils import get_shopify_product, format_shopify_send_to_store
from multichannel_products_core.master_product_helper import MasterProductHelperBase
from multichannel_products_core.utils import apply_pricing_template, apply_templates
from shopified_core import permissions
from . import tasks
from .models import ShopifyProduct, ShopifyStore


def map_variants(parent, shopify_product, mapping, store=None):
    variants = []
    parent_variants = json.loads(parent.variants_config).get('variants_info')
    parent_variants = [{'title': item,
                        'price': parent_variants[item]['price'],
                        'compare_at_price': parent_variants[item]['compare_at'],
                        } for item in parent_variants.keys()]
    for variant in shopify_product.get('variants'):
        parent_variant = list(filter(lambda x: x['title'] == mapping[variant['title']],
                                     parent_variants))
        if parent_variant:
            parent_variant = parent_variant[0]
        else:
            parent_variant = {'price': variant['price'], 'compare_at_price': variant['compare_at_price']}

        if store:
            parent_variant['price'], parent_variant['compare_at_price'] = apply_pricing_template(
                parent_variant['price'], parent_variant['compare_at_price'], store)

        variants.append({**variant,
                         'price': parent_variant['price'],
                         'compare_at_price': parent_variant['compare_at_price']})
    return variants


class ShopifyMasterProductHelper(MasterProductHelperBase):
    product_model = ShopifyProduct
    store_model = ShopifyStore

    def __init__(self, product_id=None):
        if product_id:
            self._product = (ShopifyProduct.objects
                             .select_related('master_product').select_related('store')
                             .get(id=product_id))

    def create_new_product(self, user, store_id, parent, override_fields=None, publish=False):
        store = ShopifyStore.objects.get(id=store_id)
        permissions.user_can_edit(user, store)

        product_data = self.get_master_product_mapped_data(parent, override_fields)
        product_data = apply_templates(product_data, store)

        result = tasks.export_product(
            req_data={
                'store': store.id,
                'data': json.dumps(product_data),
                'notes': parent.notes,
                'activate': True,
            },
            target='save-for-later',
            user_id=user.id
        )

        self.product = ShopifyProduct.objects.get(id=result.get('product', {}).get('id'))
        self.connect_parent_product(parent)
        self.update_master_variants_map(parent)

        if publish:
            self.send_product_to_store(user)

        return result

    def update_product(self, user, parent):
        permissions.user_can_edit(user, self.product)

        product_data = self.product.parsed
        product_data = self.get_master_product_mapped_data(parent, product_data=product_data)
        product_data = apply_templates(product_data, self.product.store)

        if not self.product.is_connected:
            product_data = {
                **product_data,
                'variants_images': json.loads(parent.variants_config).get('variants_images'),
                'variants_sku': json.loads(parent.variants_config).get('variants_sku'),
                'variants': json.loads(parent.variants_config).get('variants'),
                'variants_info': json.loads(parent.variants_config).get('variants_info'),
            }

        tasks.export_product(
            req_data={
                'store': self.product.store.id,
                'data': json.dumps({'product': product_data}),
                'product': self.product.id,
            },
            target='save-for-later',
            user_id=user.id)

        if self.product.is_connected:
            product_data = format_shopify_send_to_store(self.product.parsed)
            shopify_product = get_shopify_product(self.product.store, self.product.shopify_id)
            product_data = apply_templates(product_data, self.product.store)

            mapping = self.product.get_master_variants_map()
            product_data['product']['variants'] = map_variants(parent, shopify_product, mapping, self.product.store)

            tasks.export_product.apply_async(kwargs={
                'req_data': {
                    'store': self.product.store.id,
                    'data': json.dumps(product_data),
                    'product': self.product.id,
                },
                'target': 'shopify-update',
                'user_id': user.id
            }, countdown=0, expires=120)

        pusher = {'key': settings.PUSHER_KEY, 'channel': self.product.store.pusher_channel()}
        return {'pusher': pusher}

    def send_product_to_store(self, user):
        product_data = self.product.get_data()
        permissions.user_can_edit(user, self.product)

        tasks.export_product.apply_async(kwargs={
            'req_data': {
                'store': self.product.store.id,
                'data': json.dumps(format_shopify_send_to_store(product_data)),
                'original_url': product_data.get('original_url'),
                'product': self.product.id,
            },
            'target': 'shopify',
            'user_id': user.id
        }, countdown=0, expires=120)

        pusher = {'key': settings.PUSHER_KEY, 'channel': self.product.store.pusher_channel()}
        return {'pusher': pusher}

    def get_product_mapped_data(self):
        product = self.product
        parsed_data = product.parsed
        data = {
            'title': product.title,
            'description': parsed_data.get('description'),
            'price': product.price,
            'compare_at_price': parsed_data.get('compare_at_price'),
            'images': parsed_data.get('images'),
            'product_type': product.product_type,
            'tags': product.tags,
            'notes': product.notes,
            'original_url': parsed_data.get('original_url'),
            'vendor': parsed_data.get('vendor'),
            'published': parsed_data.get('published'),
            'variants_images': parsed_data.get('variants_images'),
            'variants_sku': parsed_data.get('variants_sku'),
            'variants': parsed_data.get('variants'),
            'variants_info': parsed_data.get('variants_info'),
            'store': {
                'name': product.default_supplier.supplier_name,
                'url': product.default_supplier.supplier_url,
            }
        }
        return data

    def get_variants(self):
        if self.product.source_id:
            product_data = get_shopify_product(self.product.store, self.product.shopify_id)
            variants_list = []
            for variant in product_data.get('variants'):
                item = variant.get('title')
                variants_list.append({
                    'title': item,
                    'image': next((item.get('src') for item in product_data.get('images', [])
                                   if item.get('id') == variant.get('image_id')), '')
                })

        else:
            product_data = self.product.parsed
            variants = product_data.get('variants', [])
            variants_images = list(product_data.get('variants_images', {}).items())
            image_url_by_hash = get_image_url_by_hash(product_data)

            titles, values = [], []
            for variant in variants:
                titles.append(variant.get('title', ''))
                values.append(variant.get('values', []))

            variants_list = []
            for product in itertools.product(*values):
                options = []
                image = ''
                for name, option in zip(titles, product):
                    options.append(option)
                    for image_hash, variant_option in variants_images:
                        if image_hash in image_url_by_hash and variant_option == option:
                            image = image_url_by_hash[image_hash]

                variant_name = ' / '.join(options)
                variants_list.append({'title': variant_name, 'image': image})

        return variants_list
