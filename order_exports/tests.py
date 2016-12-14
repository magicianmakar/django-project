from datetime import timedelta

from django.conf import settings
from django.core.urlresolvers import reverse
from django.test import TestCase
from django.utils import timezone

import factory
from factory import fuzzy

from leadgalaxy.models import ShopifyStore
from order_exports.models import OrderExport, OrderExportFilter, ORDER_STATUS, \
    ORDER_FULFILLMENT_STATUS, ORDER_FINANCIAL_STATUS, order_export_done, generate_reports


class UserFactory(factory.django.DjangoModelFactory):
    username = 'TestUser'
    first_name = fuzzy.FuzzyText()
    last_name = fuzzy.FuzzyText()
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
    title = fuzzy.FuzzyText()
    user = factory.SubFactory('order_exports.tests.UserFactory')
    version = 1

    class Meta:
        model = ShopifyStore


class OrderExportFilterFactory(factory.django.DjangoModelFactory):
    vendor = fuzzy.FuzzyText()
    status = ORDER_STATUS[0][0]
    fulfillment_status = ORDER_FULFILLMENT_STATUS[0][0]
    financial_status = ORDER_FINANCIAL_STATUS[0][0]

    class Meta:
        model = OrderExportFilter


class OrderExportFactory(factory.django.DjangoModelFactory):
    store = factory.SubFactory('order_exports.tests.ShopifyStoreFactory')
    filters = factory.SubFactory('order_exports.tests.OrderExportFilterFactory')
    description = fuzzy.FuzzyText()
    schedule = fuzzy.FuzzyDateTime(timezone.now() - timedelta(hours=24),
                                           timezone.now(),
                                           force_minute=0,
                                           force_second=0)
    receiver = 'test@rank-engine.com'
    fields = '["id", "name", "total_price", "email"]'
    line_fields = '["name", "fulfillment_status"]'
    shipping_address = '[]'

    class Meta:
        model = OrderExport


class OrderExportTestCase(TestCase):

    def setUp(self):
        order_export_done.disconnect(generate_reports, sender=OrderExport)
        self.user = UserFactory()
        self.user.set_password('pass1')
        self.user.save()

        self.store = ShopifyStoreFactory(user=self.user)
        filters = OrderExportFilterFactory()
        filters.save()
        self.order_export = OrderExportFactory(store=self.store, filters=filters)
        self.order_export.save()

        self.client.post(reverse('login'), {'username': self.user.username, 'password': 'pass1'})

    def test_add_order(self):
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
        self.assertEqual(response.status_code, 200)

        post_data['receiver'] = ''
        response = self.client.post(reverse('order_exports_add'), data=post_data)
        self.assertEqual(response.status_code, 200)

    def test_edit_order(self):
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
        self.assertEqual(response.status_code, 200)

        self.order_export.save()
        post_data['fields'] = '[]'
        # response = self.client.post(reverse('order_exports_edit', kwargs={'order_export_id': self.order_export.id}), post_data)
        # self.assertEqual(response.status_code, 200)
