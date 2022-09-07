import itertools
import json

from django.conf import settings

from bigcommerce_core.utils import get_image_url_by_hash
from multichannel_products_core.master_product_helper import MasterProductHelperBase
from multichannel_products_core.utils import apply_pricing_template, apply_templates
from shopified_core import permissions

from . import tasks
from .models import CommerceHQProduct, CommerceHQStore


def map_variants(parent, product_data, mapping, store=None):
    variants = []
    parent_variants = json.loads(parent.variants_config).get('variants_info')
    parent_variants = [{'variant': item,
                        'price': parent_variants[item]['price'],
                        'compare_at_price': parent_variants[item]['compare_at'],
                        } for item in parent_variants.keys()]
    for variant in product_data.get('variants'):
        parent_variant = list(filter(lambda x: x['variant'] == mapping[' / '.join(variant['variant'])],
                                     parent_variants))
        if parent_variant:
            parent_variant = parent_variant[0]
        else:
            parent_variant = {'price': variant['price'], 'compare_at_price': variant['compare_price']}

        if store:
            parent_variant['price'], parent_variant['compare_at_price'] = apply_pricing_template(
                parent_variant['price'], parent_variant['compare_at_price'], store)

        variants.append({'id': variant['id'], 'sku': variant['sku'],
                         'price': parent_variant['price'],
                         'compare_price': parent_variant['compare_at_price']})
    return variants


class CommerceHQMasterProductHelper(MasterProductHelperBase):
    product_model = CommerceHQProduct
    store_model = CommerceHQStore

    def __init__(self, product_id=None):
        if product_id:
            self._product = (CommerceHQProduct.objects
                             .select_related('master_product').select_related('store')
                             .get(id=product_id))

    def create_new_product(self, user, store_id, parent, override_fields=None, publish=False):
        store = CommerceHQStore.objects.get(id=store_id)
        permissions.user_can_edit(user, store)

        product_data = self.get_master_product_mapped_data(parent, override_fields=override_fields)
        product_data = apply_templates(product_data, store)

        result = tasks.product_save(
            req_data={
                'store': store.id,
                'data': json.dumps(product_data),
                'notes': parent.notes,
                'activate': True,
            },
            user_id=user.id
        )

        self.product = CommerceHQProduct.objects.get(id=result.get('product', {}).get('id'))
        self.connect_parent_product(parent)
        self.update_master_variants_map(parent)

        if publish:
            result = {'product': self.send_product_to_store(user)}

        return result

    def update_product(self, user, parent):
        permissions.user_can_edit(user, self.product)

        product_data = self.product.sync() if self.product.is_connected else self.product.parsed

        if self.product.is_connected:
            product_data = self.get_master_product_mapped_data(
                parent, product_data=product_data, override_fields={'variants': product_data.get('variants')})
            product_data = apply_templates(product_data, self.product.store)

            mapping = self.product.get_master_variants_map()
            variants = map_variants(parent, product_data, mapping, self.product.store)

            tasks.product_update.apply_async(kwargs={
                'product_id': self.product.id,
                'data': {
                    **product_data,
                    'variants': variants,
                    'compare_price': product_data.get('compare_at_price')
                },
            }, countdown=0, expires=120)
        else:
            product_data = self.get_master_product_mapped_data(parent, product_data=product_data)
            product_data = apply_templates(product_data, self.product.store)

            tasks.product_save(
                req_data={
                    'store': self.product.store.id,
                    'data': json.dumps(product_data),
                    'notes': parent.notes,
                    'activate': True,
                    'product': self.product.id,
                },
                user_id=user.id
            )

        pusher = {'key': settings.PUSHER_KEY, 'channel': self.product.store.pusher_channel()}
        return {'pusher': pusher}

    def send_product_to_store(self, user):
        permissions.user_can_edit(user, self.product)

        tasks.product_export.apply_async(kwargs={
            'user_id': user.id,
            'product_id': self.product.id,
            'store_id': self.product.store.id,
            'publish': True,
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
            product_data = self.product.sync()
            variants_list = []
            for variant in product_data.get('variants'):
                options = variant.get('variant')
                item = ' / '.join(options)
                variants_list.append({'title': item, 'image': variant.get('images', [])[0].get('path')})
        else:
            product_data = self.product.parsed
            variants = product_data.get('variants', [])
            variants_images = (product_data.get('variants_images') or {}).items()
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
