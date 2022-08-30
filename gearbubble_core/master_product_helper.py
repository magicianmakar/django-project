import json

from django.conf import settings

from multichannel_products_core.master_product_helper import MasterProductHelperBase
from shopified_core import permissions

from . import tasks
from .models import GearBubbleProduct, GearBubbleStore


class GearBubbleMasterProductHelper(MasterProductHelperBase):
    product_model = GearBubbleProduct
    store_model = GearBubbleStore

    def __init__(self, product_id=None):
        if product_id:
            self._product = (GearBubbleProduct.objects
                             .select_related('master_product').select_related('store')
                             .get(id=product_id))

    def create_new_product(self, user, store_id, parent, override_fields=None, publish=False):
        store = GearBubbleStore.objects.get(id=store_id)
        permissions.user_can_edit(user, store)

        product_data = self.get_master_product_mapped_data(parent, override_fields)

        result = tasks.product_save(
            req_data={
                'store': store.id,
                'data': json.dumps(product_data),
                'notes': parent.notes,
                'activate': True,
            },
            user_id=user.id
        )

        self.product = GearBubbleProduct.objects.get(id=result.get('product', {}).get('id'))
        self.connect_parent_product(parent)
        self.update_master_variants_map(parent)

        if publish:
            result = {'product': self.send_product_to_store(user)}

        return result

    def update_product(self, user, parent):
        permissions.user_can_edit(user, self.product)

        product_data = self.product.sync() if self.product.is_connected else self.product.parsed
        product_data = self.get_master_product_mapped_data(parent, product_data=product_data)

        tasks.product_update.apply_async(kwargs={
            'product_id': self.product.id,
            'data': product_data,
        }, countdown=0, expires=120)

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
        return []
