import json

from django.conf import settings

from ebay_core import tasks
from ebay_core.models import EbayStore, EbayProduct
from multichannel_products_core.master_product_helper import MasterProductHelperBase
from multichannel_products_core.utils import apply_pricing_template, apply_templates
from shopified_core import permissions


def map_variants(parent, product_variants, mapping, store=None):
    variants = []
    parent_variants = json.loads(parent.variants_config).get('variants_info')
    parent_variants = [{'variant': item,
                        'price': parent_variants[item]['price'],
                        'compare_at_price': parent_variants[item]['compare_at'],
                        } for item in parent_variants.keys()]
    for variant in product_variants:
        parent_variant = list(filter(lambda x: x['variant'] == mapping[variant['varianttitle']],
                                     parent_variants))
        if parent_variant:
            parent_variant = parent_variant[0]
        else:
            parent_variant = {'price': variant['price'], 'compare_at_price': variant['compareatprice']}

        compare_at_price = parent_variant['compare_at_price']
        price = parent_variant['price']

        if store:
            price, compare_at_price = apply_pricing_template(price, compare_at_price, store)

        variant['compareatprice'] = compare_at_price if compare_at_price else '0.00'
        variant['price'] = float(price) if price else 0
        variants.append(variant)
    return variants


class EbayMasterProductHelper(MasterProductHelperBase):
    product_model = EbayProduct
    store_model = EbayStore

    def __init__(self, product_id=None):
        if product_id:
            self._product = (EbayProduct.objects
                             .select_related('master_product').select_related('store')
                             .get(guid=product_id))

    def create_new_product(self, user, store_id, parent, override_fields=None, publish=False):
        store = EbayStore.objects.get(id=store_id)
        permissions.user_can_edit(user, store)

        product_data = self.get_master_product_mapped_data(parent, override_fields)
        product_data = apply_templates(product_data, store)

        for variant in (product_data.get('variants_info', {}) or {}).keys():
            price = product_data['variants_info'][variant]['price']
            compare_at = product_data['variants_info'][variant]['compare_at']

            price = float(price) if price else 0
            compare_at = compare_at if compare_at else 0
            price, compare_at = apply_pricing_template(price, compare_at, store)

            product_data['variants_info'][variant]['price'] = price
            product_data['variants_info'][variant]['compare_at'] = compare_at

        pusher_channel = store.pusher_channel()
        tasks.product_save.apply_async(kwargs={
            'req_data': {
                'store': store.id,
                'data': json.dumps(product_data),
                'notes': parent.notes,
                'activate': True,
                'master_product': parent.id
            },
            'user_id': user.id,
            'pusher_channel': pusher_channel
        })

        return {
            'product': {
                'pusher': {'key': settings.PUSHER_KEY, 'channel': pusher_channel}
            }
        }

    def update_product(self, user, parent):
        permissions.user_can_edit(user, self.product)

        product_data = self.product.parsed
        mapping = self.product.get_master_variants_map()
        variants = map_variants(parent, self.product.variants_for_details_view, mapping, self.product.store)

        product_data = {
            'guid': product_data.get('guid'),
            'title': parent.title,
            'longdescription': parent.description,
            'price': parent.price,
            'compareatprice': float(parent.compare_at_price) if parent.compare_at_price else None,
            'images': json.loads(parent.images),
            'producttype': parent.product_type,
            'tags': parent.tags,
            'notes': parent.notes,
            'original_url': parent.original_url,
            'vendor': parent.vendor,
            'published': parent.published,
            'variants': variants,
        }
        product_data = apply_templates(product_data, self.product.store, is_suredone=True)

        tasks.product_update.apply_async(kwargs={
            'user_id': user.id,
            'parent_guid': product_data.get('guid'),
            'product_data': product_data,
            'store_id': self.product.store.id,
            'skip_publishing': not self.product.is_connected
        }, countdown=0, expires=120)

        pusher = {'key': settings.PUSHER_KEY, 'channel': self.product.store.pusher_channel()}
        return {'pusher': pusher}

    def send_product_to_store(self, user):
        permissions.user_can_edit(user, self.product)

        tasks.product_export.apply_async(kwargs={
            'user_id': user.id,
            'parent_guid': self.product.guid,
            'store_id': self.product.store.id,
        }, countdown=0, expires=120)

        pusher = {
            'key': settings.PUSHER_KEY,
            'channel': self.product.store.pusher_channel()
        }

        return {
            'pusher': pusher
        }

    def get_product_mapped_data(self):
        product = self.product
        parsed_data = product.parsed
        variants_info = {item.get('varianttitle'): {
            'price': item.get('price'),
            'compare_at': item.get('compareatprice'),
            'sku': item.get('suppliersku'),
            'image': item.get('image'),
        } for item in self.product.variants_for_details_view}
        variants_sku = {item.get('varianttitle'): item.get('suppliersku') for item in
                        self.product.variants_for_details_view}
        data = {
            'title': product.title,
            'description': product.product_description,
            'price': product.price,
            'compare_at_price': parsed_data.get('compareatprice'),
            'images': json.loads(product.media_links_data),
            'product_type': product.product_type,
            'tags': product.tags,
            'notes': product.notes or '',
            'original_url': parsed_data.get('originalurl'),
            'vendor': product.default_supplier.supplier_name if product.default_supplier else '',
            'published': product.some_variants_are_connected,
            'variants_images': {},
            'variants_sku': variants_sku,
            'variants': json.loads(self.product.variants_config),
            'variants_info': variants_info,
            'store': {
                'name': product.default_supplier.supplier_name,
                'url': product.default_supplier.supplier_url,
            }
        }
        return data

    def get_variants(self):
        variants = self.product.variants_for_details_view
        variants_list = [{'title': variant['varianttitle'], 'image': variant['image']} for variant in variants]
        return variants_list
