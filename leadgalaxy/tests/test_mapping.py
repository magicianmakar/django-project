from django.test import TestCase

import json

from leadgalaxy.models import User, ShopifyStore, ShopifyProduct


class StoreTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create(username='me', email='me@localhost.com')

        self.store = ShopifyStore.objects.create(
            user=self.user, title="test1")

        self.product = ShopifyProduct.objects.create(
            user=self.user,
            data='{}',
            variants_map=json.dumps({
                '1234567': 'Red'
                }))

    def test_simple_mapping(self):
        variants_map = self.product.get_variant_mapping()
        self.assertEqual(variants_map.get('1234567'), 'Red')
        self.assertEqual(variants_map.get('1234567'), 'Red')

    def test_simple_mapping_with_name(self):
        self.assertEqual(self.product.get_variant_mapping('1234567'), 'Red')
        self.assertEqual(self.product.get_variant_mapping(1234567), 'Red')

    def test_mapping_default(self):
        self.assertEqual(self.product.get_variant_mapping('987654321', 'Blue'), 'Blue')

    def test_mapping_number(self):
        self.product.set_variant_mapping({
            '987654321': '123'
        })

        self.assertEqual(self.product.get_variant_mapping('987654321', '123'), '123')

    def test_mapping_comma_list(self):
        self.product.set_variant_mapping({
            '987654321': 'Blue,S'
        })

        self.assertEqual(self.product.get_variant_mapping('987654321'), 'Blue,S')

    def test_mapping_with_lists(self):
        self.product.set_variant_mapping({
            '987654321': ['Blue', 'S']
        })

        self.assertEqual(self.product.get_variant_mapping('987654321'), ['Blue', 'S'])

    def test_mapping_with_dicts(self):
        self.product.set_variant_mapping({
            '987654321': [{
                'title': 'Blue',
                'sku': 'sku-1-12345'
                }, {
                'title': 'S',
                'sku': 'sku-2-12345'
            }]
        })

        self.assertEqual(map(lambda e: e['title'], self.product.get_variant_mapping('987654321')), ['Blue', 'S'])
        self.assertEqual(map(lambda e: e['sku'], self.product.get_variant_mapping('987654321')), ['sku-1-12345', 'sku-2-12345'])
