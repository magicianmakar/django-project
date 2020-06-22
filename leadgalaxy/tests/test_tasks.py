import json
from unittest.mock import patch

from lib.test import BaseTestCase
from leadgalaxy.tests.factories import (
    ShopifyProductFactory,
    ShopifyStoreFactory,
    UserFactory,
    ProductSupplierFactory
)
from product_alerts.utils import get_supplier_variants

from leadgalaxy.tasks import (
    link_variants_to_new_images,
    sync_shopify_product_quantities
)


class TasksTestCase(BaseTestCase):
    def setUp(self):
        self.user = UserFactory()
        password = 'test'
        self.user.set_password(password)
        self.user.save()

        self.product = ShopifyProductFactory(user=self.user)
        self.store = ShopifyStoreFactory(user=self.user)

    def test_link_variants_to_new_images(self):
        product = self.product

        new_src = 'http://example.com/new'
        new_src_2 = 'http://example.com/new2'
        old_src = 'http://example.com/old'
        old_src_2 = 'http://example.com/old2'

        new_data = dict(
            product=dict(
                images=[{
                    'src': new_src,
                }],
            )
        )

        old_to_new_image_url = json.dumps({
            old_src: new_src,
            old_src_2: new_src_2,
        })

        req_data = {'old_to_new_url': old_to_new_image_url}

        mock_product = dict(
            images=[{
                'src': old_src,
                'variant_ids': [1, 2],
            }, {
                'src': 'non-existing',
            }, {
                'src': old_src_2,
            }],
        )

        with patch('leadgalaxy.tasks.utils.get_shopify_product',
                   return_value=mock_product):
            updated_new_data = link_variants_to_new_images(product,
                                                           new_data,
                                                           req_data)

        new_images = updated_new_data['product']['images']
        self.assertEqual(new_images[0]['src'], new_src)
        self.assertEqual(new_images[0]['variant_ids'], [1, 2])

    def test_sync_inventory_with_supplier(self):
        product = ShopifyProductFactory(
            store=self.store, user=self.user, source_id=12345678,
            data='''{"store": {
                "name": "Suplier 1",
                "url": "https://www.aliexpress.com/item/32815997098.html"
            }}''')

        supplier = ProductSupplierFactory(product=product, product_url='https://www.aliexpress.com/item/32815997098.html')

        product.default_supplier = supplier
        product.variants_map = json.dumps({
            '32146941476915': json.dumps([
                {
                    'title': 'CHINA',
                    'sku': '200007763:201336100'
                },
                {
                    'title': '19 PCS Yellow',
                    'sku': '14:365462'
                }
            ]),
        })
        product.save()

        product_data = dict(
            variants=[{
                'id': 32146941476915,
                'product_id': 4566069936179,
                'title': '19 PCS Yellow',
                'price': '42.95',
                'sku': '14:365462',
                'inventory_policy': 'deny',
                'option1': '19 PCS Yellow',
                'option2': None,
                'option3': None,
                'inventory_item_id': 34005719449651,
                'inventory_quantity': 7167,
                'old_inventory_quantity': 7167,
            }]
        )

        aliexpress_data = get_supplier_variants('aliexpress', supplier.get_source_id())

        with patch('leadgalaxy.models.ShopifyProduct.set_variant_quantity') as mock_set_variant_quantity, \
                patch('leadgalaxy.utils.get_shopify_product', return_value=product_data):
            sync_shopify_product_quantities(product.id)
            mock_set_variant_quantity.assert_called_with(
                quantity=aliexpress_data[1]['availabe_qty'],
                variant=product_data['variants'][0]
            )
