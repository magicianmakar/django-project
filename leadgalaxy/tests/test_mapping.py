from django.test import TransactionTestCase

import json

from leadgalaxy.models import User, ShopifyStore, ShopifyProduct, ProductSupplier


class MappingTestCase(TransactionTestCase):

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

    def test_mapping_comma_list_for_extension(self):
        self.product.set_variant_mapping({
            '987654321': 'Blue,S'
        })

        self.assertEqual(self.product.get_variant_mapping('987654321', for_extension=True), ['Blue', 'S'])

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

    def test_mapping_with_dicts_saved_as_str(self):
        self.product.set_variant_mapping({
            '1708819152926': '[{"title": "black"}, {"title": "S"}]',
            '1708819218462': '[{"title": "black"}, {"title": "M"}]',
            '1708819349534': '[{"title": "black"}, {"title": "L"}]',
        })

        mapping = self.product.get_variant_mapping(for_extension=True)
        self.assertEqual(len(mapping), 3)
        self.assertNotEqual(set(map(lambda e: type(e), mapping.values())), {str, })
        self.assertEqual(map(lambda e: e['title'], mapping['1708819218462']), ['black', 'M'])

    def test_default_supplier_mapping(self):
        supplier1 = ProductSupplier.objects.create(
            store=self.store,
            product=self.product,
        )

        supplier2 = ProductSupplier.objects.create(
            store=self.store,
            product=self.product,
        )

        self.product.set_default_supplier(supplier1)

        self.product.set_variant_mapping({
            '987654321': 'Blue,S'
        })

        self.assertIsNotNone(supplier1.variants_map)
        self.assertIsNone(supplier2.variants_map)

    def test_select_supplier_mapping(self):
        supplier1 = ProductSupplier.objects.create(
            store=self.store,
            product=self.product,
        )

        supplier2 = ProductSupplier.objects.create(
            store=self.store,
            product=self.product,
        )

        self.product.set_default_supplier(supplier1)

        self.product.set_variant_mapping(
            {
                '987654321': 'Blue,S'
            },
            supplier=supplier2
        )

        self.assertIsNotNone(supplier2.variants_map)
        self.assertIsNone(supplier1.variants_map)
