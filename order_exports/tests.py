from datetime import timedelta

import factory
import requests_mock
from django.conf import settings
from django.core.urlresolvers import reverse
from django.test import TestCase
from django.utils import timezone
from factory import fuzzy

from leadgalaxy.models import ShopifyStore
from order_exports.models import OrderExport, OrderExportFilter, ORDER_STATUS, \
    ORDER_FULFILLMENT_STATUS, ORDER_FINANCIAL_STATUS


class UserFactory(factory.django.DjangoModelFactory):
    username = 'TestUser'
    first_name = factory.fuzzy.FuzzyText()
    last_name = factory.fuzzy.FuzzyText()
    is_active = True
 
    class Meta:
        model = settings.AUTH_USER_MODEL


class ShopifyStoreFactory(factory.django.DjangoModelFactory):
    access_token = None
    api_url = 'https://test:test@test-store.myshopify.com'
    is_active = True
    list_index = 0
    scope = None
    shop = None
    title = factory.fuzzy.FuzzyText()
    user = factory.SubFactory('order_exports.tests.UserFactory')
    version = 1

    class Meta:
        model = ShopifyStore


class OrderExportFilterFactory(factory.django.DjangoModelFactory):
    vendor = factory.fuzzy.FuzzyText()
    status = ORDER_STATUS[0][0]
    fulfillment_status = ORDER_FULFILLMENT_STATUS[0][0]
    financial_status = ORDER_FINANCIAL_STATUS[0][0]

    class Meta:
        model = OrderExportFilter


class OrderExportFactory(factory.django.DjangoModelFactory):
    store = factory.SubFactory('order_exports.tests.ShopifyStoreFactory')
    filters = factory.SubFactory('order_exports.tests.OrderExportFilterFactory')
    description = factory.fuzzy.FuzzyText()
    schedule = factory.fuzzy.FuzzyDateTime(timezone.now() - timedelta(hours=24),
                                           timezone.now(), 
                                           force_minute=0, 
                                           force_second=0)
    receiver = 'test@rank-engine.com'
    fields = '["id", "name", "total_price", "email"]'
    line_fields = '["name", "fulfillment_status"]'
    shipping_address = '[]'


    class Meta:
        model = OrderExport


@requests_mock.Mocker()
class OrderExportTestCase(TestCase):

    def setUp(self):
        self.user = UserFactory()
        self.user.set_password('pass1')
        self.user.save()

        self.store = ShopifyStoreFactory(user=self.user)
        filters = OrderExportFilterFactory()
        self.order_export = OrderExportFactory(store=self.store, filters=filters)

        self.client.post(reverse('login'), {'username': self.user.username, 'password': 'pass1'})

    def test_add_order(self, mock):
        post_data = {
            'store': 1,
            'schedule': '12:00',
            'receiver': 'guilherme.dcosta@gmail.com',
            'description': 'Testing Order Export',
            'fields': '["fields_id", "fields_name", "fields_total_price", "fields_email"]',
            'shipping_address': '[]',
            'line_fields': '[]',
            'vendor': '',
            'status': 'any',
            'fulfillment_status': 'any',
            'financial_status': 'authorized'
        }

        response = self.client.post(reverse('order_exports_add'), post_data)
        self.assertEqual(response.status_code, 302)

        post_data['receiver'] = ''
        response = self.client.post(reverse('order_exports_add'), data=post_data)
        self.assertEqual(response.status_code, 200)

    def test_edit_order(self, mock):
        post_data = {
            'store': 1,
            'schedule': '12:00',
            'receiver': 'guilherme.dcosta@gmail.com',
            'description': 'Testing Order Export',
            'fields': '["fields_id", "fields_name", "fields_total_price", "fields_email"]',
            'shipping_address': '[]',
            'line_fields': '[]',
            'vendor': '',
            'status': 'any',
            'fulfillment_status': 'any',
            'financial_status': 'authorized'
        }

        response = self.client.post(reverse('order_exports_edit', kwargs={'order_export_id': self.order_export.id}), post_data)
        self.assertEqual(response.status_code, 302)

        post_data['fields'] = '[]'
        response = self.client.post(reverse('order_exports_edit', kwargs={'order_export_id': self.order_export.id}), post_data)
        self.assertEqual(response.status_code, 200)

