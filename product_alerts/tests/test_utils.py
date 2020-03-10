from lib.test import BaseTestCase
from unittest.mock import patch

from django.conf import settings
from django.test import tag

from ..utils import (
    get_supplier_variants,
    monitor_product,
    match_sku_with_mapping_sku,
    match_sku_with_shopify_sku,
    match_sku_title_with_mapping_title,
    match_sku_title_with_shopify_variant_title,
    variant_index_from_supplier_sku
)
from leadgalaxy import utils
from leadgalaxy.models import ShopifyProduct, ProductSupplier


class UtilTestCase(BaseTestCase):
    fixtures = ['product_changes.json']

    def setUp(self):
        self.product_id = 32825336375
        self.monitor_id = 1

    def test_get_supplier_variants(self):
        if not settings.ALIEXPRESS_TOKEN:
            return

        variants = get_supplier_variants('aliexpress', self.product_id)

        self.assertEqual(len(variants), 8)

        for v in variants:
            self.assertIn('sku', v)
            self.assertIn(';', v['sku'])
            self.assertIn('availabe_qty', v)
            self.assertGreaterEqual(v['availabe_qty'], 0)

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
        if 'price' not in variants[0]:
            return

        # If a shopify variant was not mapped with a specific aliexpress variant,
        # "ships from" country for the shopify variant is China
        index = variant_index_from_supplier_sku(product, '14:1254#Sky Blue;5:361385#L;200007763:201336100#China', variants)
        self.assertIsNotNone(index)
        self.assertEqual(variants[index]['option1'], 'Sky Blue')
        self.assertEqual(variants[index]['option2'], 'L')

        # Couldn't find a variant mapped with Russian variants
        index = variant_index_from_supplier_sku(product, '14:1254#Sky Blue;5:361385#L;200007763:201336103#Russian Federation', variants)
        self.assertIsNotNone(index)
        self.assertEqual(variants[index]['option1'], 'Sky Blue')
        self.assertEqual(variants[index]['option2'], 'L')

        supplier = ProductSupplier.objects.get(pk=8)
        product.set_default_supplier(supplier)
        # Sky Blue/L variant was mapped to a variant shipped from Russia
        index = variant_index_from_supplier_sku(product, '14:1254#Sky Blue;5:361385#L;200007763:201336103#Russian Federation', variants)
        self.assertIsNotNone(index)
        self.assertEqual(variants[index]['option1'], 'Sky Blue')
        self.assertEqual(variants[index]['option2'], 'L')


class MappingUtilsTestCase(BaseTestCase):
    fixtures = ['product_changes.json']

    def setUp(self):
        self.product_id = 32825336375
        self.monitor_id = 1

    def test_sku_compare_old_mapping(self):
        ali_sku = '1100:472496#Red;774888:361385#L'
        mapping = [
            {"title": "Red", "sku": "sku-1-472496"},
            {"title": "L", "sku": "sku-2-361385"}
        ]
        self.assertTrue(match_sku_with_mapping_sku(ali_sku, mapping))

        ali_sku = '1100:472496#Red;774888:361385'
        self.assertTrue(match_sku_with_mapping_sku(ali_sku, mapping))

        ali_sku = '1100:472496;774888:361385'
        self.assertTrue(match_sku_with_mapping_sku(ali_sku, mapping))

        ali_sku = '1100:472491#Red;774888:361385#L'
        self.assertFalse(match_sku_with_mapping_sku(ali_sku, mapping))

    def test_sku_compare_old_mapping_sorting(self):
        ali_sku = '1100:472496#Red;774888:361385#L'
        mapping = [
            {"title": "L", "sku": "sku-2-361385"},
            {"title": "Red", "sku": "sku-1-472496"},
        ]
        self.assertTrue(match_sku_with_mapping_sku(ali_sku, mapping))

        ali_sku = '774888:361385;1100:472491'
        self.assertFalse(match_sku_with_mapping_sku(ali_sku, mapping))

    def test_sku_compare_mapping(self):
        ali_sku = '1100:472496#Red;774888:361385#L'
        mapping = [
            {"title": "Red", "sku": "1100:472496"},
            {"title": "L", "sku": "774888:361385"}
        ]

        self.assertTrue(match_sku_with_mapping_sku(ali_sku, mapping))
        ali_sku = '1100:472496;774888:361385#L'

        self.assertTrue(match_sku_with_mapping_sku(ali_sku, mapping))
        ali_sku = '1100:472496;774888:361385'
        self.assertTrue(match_sku_with_mapping_sku(ali_sku, mapping))

        ali_sku = '1100:472490#Red;774888:361380#L'
        self.assertFalse(match_sku_with_mapping_sku(ali_sku, mapping))

    def test_sku_compare_mapping_ignore_shipping(self):
        ali_sku = '14:1254#Sky Blue;5:361385#L;200007763:201336103#Russian Federation'
        mapping = [
            {"title": "Sky Blue", "sku": "14:1254"},
            {"title": "L", "sku": "5:361385"}
        ]

        self.assertTrue(match_sku_with_mapping_sku(ali_sku, mapping))

    def test_sku_compare_mapping_do_not_ignore_shipping(self):
        ali_sku = '14:1254#Sky Blue;5:361385#L;200007763:201336103#Russian Federation'
        mapping = [
            {"title": "Sky Blue", "sku": "14:1254"},
            {"title": "L", "sku": "5:361385"},
            {"title": "China", "sku": "200007763:201336101"},
        ]

        self.assertFalse(match_sku_with_mapping_sku(ali_sku, mapping))

    def test_sku_compare_mapping_sorting(self):
        ali_sku = '1100:472496#Red;774888:361385#L'
        mapping = [
            {"title": "Red", "sku": "1100:472496"},
            {"title": "L", "sku": "774888:361385"},
        ]

        self.assertTrue(match_sku_with_mapping_sku(ali_sku, mapping))

        ali_sku = '774888:361385;1100:472496#Red'
        self.assertTrue(match_sku_with_mapping_sku(ali_sku, mapping))

    def test_sku_compare_with_shopify_sku(self):
        ali_sku = '1100:472496#Red;774888:361385#L'
        shopify_sku = '1100:472496;774888:361385'

        self.assertTrue(match_sku_with_shopify_sku(ali_sku, shopify_sku))

    def test_sku_compare_with_shopify_sku_sort(self):
        ali_sku = '1100:472496#Red;774888:361385#L'
        shopify_sku = '774888:361385;1100:472496'

        self.assertTrue(match_sku_with_shopify_sku(ali_sku, shopify_sku))

    def test_sku_compare_with_shopify_sku_null(self):
        sku = '1100:472496#Red;774888:361385#L'

        self.assertFalse(match_sku_with_shopify_sku(None, sku))
        self.assertFalse(match_sku_with_shopify_sku(sku, None))

    def test_sku_compare_with_shopify_sku_ignore_shipping(self):
        ali_sku = '14:1254#Sky Blue;5:361385#L;200007763:201336103#Russian Federation'
        shopify_sku = '14:1254;5:361385'

        self.assertTrue(match_sku_with_shopify_sku(ali_sku, shopify_sku))

    def test_sku_compare_with_shopify_sku_do_not_ignore_shipping(self):
        ali_sku = '14:1254#Sky Blue;5:361385#L;200007763:201336103#Russian Federation'
        shopify_sku = '14:1254;5:361385;200007763:201336101'

        self.assertFalse(match_sku_with_shopify_sku(ali_sku, shopify_sku))

    def test_sku_compare_with_random_sku(self):
        ali_sku = '5:201441335#20x25cm'
        shopify_sku = '9421179-20x30cm-bag-pack'

        self.assertFalse(match_sku_with_shopify_sku(ali_sku, shopify_sku))

    def test_sku_title_compare_with_mapping(self):
        ali_sku = '1100:472496#Red;774888:361385#L'
        mapping = [
            {"title": "Red", "sku": "1100:472496"},
            {"title": "L", "sku": "774888:361385"}
        ]

        self.assertTrue(match_sku_title_with_mapping_title(ali_sku, mapping))

    def test_sku_title_compare_with_mapping_sort(self):
        ali_sku = '1100:472496#Red;774888:361385#L'
        mapping = [
            {"title": "L", "sku": "774888:361385"},
            {"title": "Red", "sku": "1100:472496"},
        ]

        self.assertTrue(match_sku_title_with_mapping_title(ali_sku, mapping))

    def test_sku_title_compare_with_mapping_sort_cs(self):
        ali_sku = '1100:472496#red;774888:361385#l'
        mapping = [
            {"title": "L", "sku": "774888:361385"},
            {"title": "RED", "sku": "1100:472496"},
        ]

        self.assertTrue(match_sku_title_with_mapping_title(ali_sku, mapping))

    def test_sku_title_compare_with_mapping_list(self):
        ali_sku = '1100:472496#red;774888:361385#l'
        mapping = ["L", "RED"]

        self.assertTrue(match_sku_title_with_mapping_title(ali_sku, mapping))

    def test_sku_title_compare_with_shopify_variant_title(self):
        ali_sku = '1100:472496#Red;774888:361385#L'
        variant = {
            "option1": "Red",
            "option2": "L",
            "option3": None,
            "sku": "774888:361385;1100:472496",
        }

        self.assertTrue(match_sku_title_with_shopify_variant_title(ali_sku, variant))

    def test_sku_title_compare_with_shopify_variant_title_sort(self):
        ali_sku = '1100:472496#Red;774888:361385#L'
        variant = {
            "option1": "L",
            "option2": "Red",
            "option3": None,
            "sku": "774888:361385;1100:472496",
        }

        self.assertTrue(match_sku_title_with_shopify_variant_title(ali_sku, variant))

    @tag('slow', 'excessive')
    def test_variant_from_supplier_with_product_title_mapping(self):
        product = ShopifyProduct.objects.get(pk=5)
        product_data = utils.get_shopify_product(product.store, product.shopify_id)
        variants = product_data['variants']
        self.assertTrue(variants)

        index = variant_index_from_supplier_sku(product, '14:175#RG black;200000858:201447586#110CM', variants)
        self.assertIsNotNone(index)
        self.assertEqualCaseInsensitive(variants[index]['option1'], 'RG black')
        self.assertEqualCaseInsensitive(variants[index]['option2'], '110CM')
