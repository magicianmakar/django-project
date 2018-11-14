import csv
from StringIO import StringIO

import requests_mock
from django.conf import settings
from django.urls import reverse
from lib.test import BaseTestCase

import factory
from factory import fuzzy

from leadgalaxy.models import ShopifyStore
from order_imports.api import ShopifyOrderImportAPI


class UserFactory(factory.django.DjangoModelFactory):
    username = 'TestUser'
    first_name = fuzzy.FuzzyText()
    last_name = fuzzy.FuzzyText()
    is_active = True

    class Meta:
        model = settings.AUTH_USER_MODEL


class ShopifyStoreFactory(factory.django.DjangoModelFactory):
    access_token = None
    api_url = 'https://:88937df17024aa5126203507e2147f47@shopified-app-ci.myshopify.com'
    is_active = True
    list_index = 0
    scope = None
    shop = None
    title = 'uncommonnow'
    user = factory.SubFactory('order_exports.tests.UserFactory')
    version = 1

    class Meta:
        model = ShopifyStore


class OrderImportReadOrdersTestCase(BaseTestCase):

    def setUp(self):
        self.user = UserFactory(username='test')
        self.password = 'test'
        self.user.set_password(self.password)
        self.user.save()

        self.client.login(username=self.user.username, password=self.password)

        self.store = ShopifyStoreFactory(user=self.user)
        self.api = ShopifyOrderImportAPI(store=self.store)

        csv_file = StringIO()
        csv_file.seek(0)
        writer = csv.DictWriter(csv_file, fieldnames=['order_name', 'line_item', 'tracking_number'])
        writer.writeheader()
        writer.writerow({'order_name': '#1089', 'line_item': '7374191301', 'tracking_number': '123456'})
        writer.writerow({'order_name': '#1089', 'line_item': '911761-black-frame-gray', 'tracking_number': '654321'})
        writer.writerow({'order_name': '#1039', 'line_item': '4175570565', 'tracking_number': '7890'})
        csv_file.seek(0)

        headers = {
            'order_id': 0,
            'line_item': 1,
            'tracking_number': 2,
        }
        self.orders = self.api.read_csv_file(csv_file, headers)

        self.empty_orders = self.api.read_csv_file(StringIO(), headers)

    def test_line_items_with_same_order_merged(self):
        self.assertEqual(self.orders, {
            '#1089': {'items': [
                {'tracking_number': '123456', 'shopify': None, 'key': '7374191301'},
                {'tracking_number': '654321', 'shopify': None, 'key': '911761-black-frame-gray'}
            ], 'shopify': None, 'name': '#1089'},
            '#1039': {'items': [
                {'tracking_number': '7890', 'shopify': None, 'key': '4175570565'}
            ], 'shopify': None, 'name': '#1039'}
        })

    def test_malformed_or_empty_data(self):
        self.assertEqual(self.empty_orders, {})


class OrderImportFetchOrdersTestCase(BaseTestCase):

    def setUp(self):
        self.user = UserFactory(username='test')
        self.password = 'test'
        self.user.set_password(self.password)
        self.user.save()

        self.client.login(username=self.user.username, password=self.password)

        self.store = ShopifyStoreFactory(user=self.user)
        self.api = ShopifyOrderImportAPI(store=self.store)

        csv_file = StringIO()
        csv_file.seek(0)
        writer = csv.DictWriter(csv_file, fieldnames=['order_name', 'line_item', 'tracking_number'])
        writer.writeheader()
        writer.writerow({'order_name': '#1089', 'line_item': '7374191301', 'tracking_number': '123456'})
        writer.writerow({'order_name': '#1089', 'line_item': '911761-black-frame-gray', 'tracking_number': '654321'})
        writer.writerow({'order_name': '#1039', 'line_item': '4175570565', 'tracking_number': '7890'})
        csv_file.seek(0)

        raw_headers = {
            'order_id_position': '1',
            'order_id_name': '',
            'line_item_position': '2',
            'line_item_name': '',
            'tracking_number_position': '3',
            'tracking_number_name': '',
            'identify_column_position': '',
            'identify_column_name': '',
        }

        headers = self.api.parse_headers(csv_file, raw_headers)
        self.orders = self.api.read_csv_file(csv_file, headers)

    def test_found_shopify_filled_for_items(self):
        with requests_mock.mock(real_http=True) as mock:
            mock.register_uri('GET', 'https://:88937df17024aa5126203507e2147f47@shopified-app-ci.myshopify.com/admin/orders.json?name=1089', json={
                "orders": [
                    {"id": 4154418757, "line_items": [
                        {"id": 7374191301, "sku": "1100195-bulbasaur"},
                        {"id": 7586832197, "sku": "911761-black-frame-gray"}
                    ]}
                ]
            })

            mock.register_uri('GET', 'https://:88937df17024aa5126203507e2147f47@shopified-app-ci.myshopify.com/admin/orders.json?name=1039', json={
                "orders": [
                    {"id": 4154418758, "line_items": [
                        {"id": 4175570565, "sku": "1100195-bulbasaur"},
                        {"id": 7586832197, "sku": "911761-black-frame-gray"}
                    ]}
                ]
            })

            self.orders = self.api.find_orders(self.orders)

            for name, order in self.orders.items():
                self.assertTrue(order['shopify'] is not None)

                for item in order['items']:
                    self.assertTrue(item['shopify'] is not None)


class OrderImportSyncShopifyTestCase(BaseTestCase):

    def setUp(self):
        self.user = UserFactory(username='test')
        self.password = 'test'
        self.user.set_password(self.password)
        self.user.save()

        self.client.login(username=self.user.username, password=self.password)

        self.store = ShopifyStoreFactory(user=self.user)
        self.api = ShopifyOrderImportAPI(store=self.store)

        tracking_items = [
            {'order_id': '4154418757', 'line_item_id': '7586832133', 'tracking_number': '123456'},
            {'order_id': '4154418757', 'line_item_id': '7586832135', 'tracking_number': '654321'},
            {'order_id': '4095014149', 'line_item_id': '7480604549', 'tracking_number': '654321'}
        ]

        with requests_mock.mock(real_http=True) as mock:
            base = 'https://:88937df17024aa5126203507e2147f47@shopified-app-ci.myshopify.com'
            mock.register_uri('POST', base + '/admin/orders/4154418757/fulfillments.json', json={})
            mock.register_uri('POST', base + '/admin/orders/4095014149/fulfillments.json', json={})

            self.tracking_response = self.api.send_tracking_number(tracking_items)

        with requests_mock.mock(real_http=True) as mock:
            base = 'https://:88937df17024aa5126203507e2147f47@shopified-app-ci.myshopify.com'
            mock.register_uri('POST', base + '/admin/orders/4154418757/fulfillments.json', json={})

            self.incomplete_tracking_response = self.api.send_tracking_number(tracking_items)

    def test_tracking_number_success_response(self):
        self.assertTrue(self.tracking_response)

    def test_tracking_number_incomplete_response(self):
        self.assertFalse(self.incomplete_tracking_response)
