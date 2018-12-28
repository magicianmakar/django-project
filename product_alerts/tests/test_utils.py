from lib.test import BaseTestCase
from mock import patch

from ..utils import (
    aliexpress_variants,
    monitor_product,
    variant_index
)
from leadgalaxy import utils
from leadgalaxy.models import ShopifyProduct, ProductSupplier


class UtilTestCase(BaseTestCase):
    fixtures = ['product_changes.json']

    def setUp(self):
        self.product_id = 32825336375
        self.monitor_id = 1

    @patch('product_alerts.utils.requests.get')
    def test_aliexpress_variants(self, mock_get):
        mock_get.return_value.json.return_value = ['test variant']
        variants = aliexpress_variants(self.product_id)
        self.assertEqual(len(variants), 1)

    @patch('product_alerts.utils.requests.post')
    def test_monitor_not_registered_product(self, mock_post):
        mock_post.return_value.json.return_value = {'id': self.monitor_id}
        product = ShopifyProduct.objects.get(pk=4)
        monitor_product(product)
        self.assertEqual(product.monitor_id, self.monitor_id)

    @patch('product_alerts.utils.requests.patch')
    def test_monitor_registered_product(self, mock_patch):
        product = ShopifyProduct.objects.get(pk=4)
        product.monitor_id = 1
        monitor_product(product)
        self.assertTrue(mock_patch.called)

    @patch('product_alerts.utils.requests.delete')
    def test_monitor_invalid_product(self, mock_delete):
        product = ShopifyProduct.objects.get(pk=4)
        product.monitor_id = 1
        product.default_supplier.product_url = ''
        monitor_product(product)
        self.assertTrue(mock_delete.called)

    def test_variant_index_with_ships_from(self):
        product = ShopifyProduct.objects.get(pk=6)
        product_data = utils.get_shopify_product(product.store, product.shopify_id)
        variants = product_data['variants']

        # If a shopify variant was not mapped with a specific aliexpress variant,
        # "ships from" country for the shopify variant is China
        index = variant_index(product, '14:1254#Sky Blue;5:361385#L;200007763:201336100#China', variants, '201336100', 'China')
        self.assertIsNotNone(index)
        variant = variants[index]
        self.assertEqual(variants[index]['option1'], 'Sky Blue')
        self.assertEqual(variants[index]['option2'], 'L')

        # Couldn't find a variant mapped with Russian variants
        index = variant_index(product, '14:1254#Sky Blue;5:361385#L;200007763:201336103#Russian Federation', variants, '201336103', 'Russian Federation')
        self.assertIsNone(index)

        supplier = ProductSupplier.objects.get(pk=8)
        product.set_default_supplier(supplier)
        # Sky Blue/L variant was mapped to a variant shipped from Russia
        index = variant_index(product, '14:1254#Sky Blue;5:361385#L;200007763:201336103#Russian Federation', variants, '201336103', 'Russian Federation')
        self.assertIsNotNone(index)
        self.assertEqual(variants[index]['option1'], 'Sky Blue')
        self.assertEqual(variants[index]['option2'], 'L')
