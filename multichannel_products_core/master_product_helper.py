import json

from typing import Optional

from multichannel_products_core.models import MasterProduct
from shopified_core import permissions


class MasterProductHelperBase:
    _product = None
    product_model = None
    store_model = None

    @property
    def product(self):
        return self._product

    @product.setter
    def product(self, p):
        self._product = p

    def check_user_permissions(self, user, action):
        if action == 'edit':
            permissions.user_can_edit(user, self.product)
        if action == 'view':
            permissions.user_can_view(user, self.product)
        if action == 'add':
            permissions.user_can_add(user, self.product)
        if action == 'delete':
            permissions.user_can_delete(user, self.product)

    def get_master_product_mapped_data(self, parent, product_data=None, override_fields=None):
        """
        Get master product mapped data for child fields.

        :param parent:
        :type parent: MasterProduct
        :param override_fields: Fields to override for child product
        :type override_fields:
        :param product_data: Child product data
        :type product_data:
        """
        if product_data is None:
            product_data = {}
        if override_fields is None:
            override_fields = {}
        data = {
            **product_data,
            'title': parent.title,
            'description': parent.description,
            'price': parent.price,
            'compare_at_price': float(parent.compare_at_price) if parent.compare_at_price else None,
            'images': json.loads(parent.images),
            'type': parent.product_type,
            'tags': parent.tags,
            'notes': parent.notes,
            'original_url': parent.original_url,
            'vendor': parent.vendor,
            'published': parent.published,
            'variants_images': json.loads(parent.variants_config).get('variants_images'),
            'variants_sku': json.loads(parent.variants_config).get('variants_sku'),
            'variants': json.loads(parent.variants_config).get('variants'),
            'variants_info': json.loads(parent.variants_config).get('variants_info'),
            **override_fields,
        }
        return data

    def create_new_product(self, user, store_id, parent, override_fields, publish=False):
        """
        Creates a product from a parent product.

        :param user:
        :type user:
        :param store_id:
        :type store_id:
        :param parent:
        :type parent: MasterProduct
        :param override_fields: Fields to override for child product
        :type override_fields:
        :param publish:
        :type publish:
        """
        raise NotImplementedError('Create New Product')

    def update_product(self, user, parent):
        """
        Updates a product with a parent product values by overwriting all values.

        :param user:
        :type user:
        :param parent:
        :type parent: MasterProduct
        """
        raise NotImplementedError('Update Product')

    def send_product_to_store(self, user):
        """
        Sends a product to store.

        :param user:
        :type user:
        """
        raise NotImplementedError('Send Product To Store')

    def get_product_mapped_data(self):
        """
        Get parent mapped fields data from child.
        """
        raise NotImplementedError('Get Product Mapped Data')

    def connect_parent_product(self, parent: Optional[MasterProduct]):
        """
        Connect passed master product to child.

        :param parent:
        :type parent: MasterProduct
        """
        self.product.master_product = parent
        self.product.save()

        if parent:
            self.update_master_variants_map(parent)

    def is_master_product_connected(self):
        """
        Check if child product connected to master.

        :return:
        :rtype: bool
        """
        return bool(self.product.master_product)

    def get_variants(self):
        """
        Get child product variants.
        """
        raise NotImplementedError('Get Child Variants')

    def update_master_variants_map(self, parent, overwrite=True):
        child_variants = self.get_variants()
        mapping = {} if overwrite else self.product.get_master_variants_map()
        if not overwrite:
            for key in list(mapping.keys()):
                if key not in [item.get('title') for item in child_variants]:
                    del mapping[key]

        for variant in child_variants:
            if not mapping.get(variant.get('title')):
                related_master_variant = next(
                    (item.get('title') for item in parent.variants_data if
                     item.get('title') == variant.get('title') or item.get('title') in variant.get(
                         'title') or variant.get('title') in item.get('title')),
                    None)
                mapping[variant.get('title')] = related_master_variant
        self.product.set_master_variants_map(mapping)
        return mapping
