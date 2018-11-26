from lib.test import BaseTestCase

from ..utils import (
    aliexpress_variants,
    variant_index
)
from leadgalaxy import utils
from leadgalaxy.models import ShopifyProduct, ProductSupplier


class UtilTestCase(BaseTestCase):
    fixtures = ['product_changes.json']

    def setUp(self):
        self.product_id = 32825336375

    def test_aliexpress_variants(self):
        variants = aliexpress_variants(self.product_id)
        self.assertEqual(len(variants), 8)

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
