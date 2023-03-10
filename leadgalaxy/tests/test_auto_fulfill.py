from django.utils import timezone
from django.test import tag
from django.core.management import call_command

from lib.test import BaseTestCase
from shopify_orders.models import ShopifyOrder, ShopifyOrderLine, ShopifyOrderLog
from leadgalaxy import utils
from leadgalaxy.models import (
    ShopifyOrderTrack,
    ShopifyStore
)

import factory

from unittest.mock import patch, Mock

from . import factories as f


class ShopifyOrderTrackFactory(factory.django.DjangoModelFactory):

    class Meta:
        model = ShopifyOrderTrack
        django_get_or_create = ['line_id', 'order_id', 'user']

    line_id = factory.fuzzy.FuzzyInteger(1000000, 9999999)
    order_id = '5415135175'
    source_tracking = 'MA7565915257226HK'
    user = factory.SubFactory('leadgalaxy.tests.factories.UserFactory')
    store_id = 1
    status_updated_at = timezone.now()


class ShopifyOrderLogFactory(factory.django.DjangoModelFactory):

    class Meta:
        model = ShopifyOrderLog
        django_get_or_create = ['order_track_id', 'store_id', 'user_id']

    order_track_id = '1654810'
    user_id = 1
    store_id = 1
    data = ''
    updated_at = timezone.now()


class ShopifyStoreFactory(factory.django.DjangoModelFactory):

    class Meta:
        model = ShopifyStore
        django_get_or_create = ['api_url']

    title = 'uncommonnow'
    api_url = 'https://:88937df17024aa5126203507e2147f47@shopified-app-ci.myshopify.com'
    user = factory.SubFactory('leadgalaxy.tests.factories.UserFactory')
    is_active = True
    auto_fulfill = 'enable'


class ShopifyOrderFactory(factory.django.DjangoModelFactory):

    class Meta:
        model = ShopifyOrder
        django_get_or_create = ['order_id']

    order_id = '5415135175'
    country_code = 'US'
    user = factory.SubFactory('leadgalaxy.tests.factories.UserFactory')
    store_id = 1
    order_number = 31
    total_price = 100
    customer_id = 1
    items_count = 1
    fulfillment_status = ''
    created_at = utils.timezone.now()
    updated_at = utils.timezone.now()


class ShopifyOrderLineFactory(factory.django.DjangoModelFactory):

    class Meta:
        model = ShopifyOrderLine
        django_get_or_create = ['line_id']

    line_id = '1654811'
    shopify_product = 10000
    price = 10
    quantity = 100
    variant_id = 12345
    order = factory.SubFactory(ShopifyOrderFactory)


class AutoFulfillTestCase(BaseTestCase):

    def setUp(self):
        self.parent_user = f.UserFactory()
        self.user = f.UserFactory()
        self.password = 'test'
        self.user.set_password(self.password)
        self.user.save()

        self.store = ShopifyStoreFactory()

    @tag('slow')
    @patch('requests.head', Mock())
    @patch('leadgalaxy.management.commands.auto_fulfill.Command.write', Mock())
    @patch('leadgalaxy.management.commands.auto_fulfill.Command.fulfill_order')
    def test_fulfill_tracked_order(self, fulfill_order):
        track = ShopifyOrderTrackFactory(
            order_id='5415135170',
            line_id='1654810',
            source_tracking='MA7565915257226HK',
            store_id=self.store.id
        )

        track.save()

        call_command('auto_fulfill')

        fulfill_order.assert_called_with(track)

    @tag('slow')
    @patch('requests.head', Mock())
    @patch('leadgalaxy.management.commands.auto_fulfill.Command.write', Mock())
    @patch('leadgalaxy.management.commands.auto_fulfill.Command.fulfill_order')
    def test_fulfill_ignore_no_tracking_number(self, fulfill_order):
        track = ShopifyOrderTrackFactory(
            order_id='5415135170',
            line_id='1654810',
            source_tracking='',
            store_id=self.store.id
        )

        track.status_updated_at = timezone.now() - timezone.timedelta(seconds=61)
        track.save()

        call_command('auto_fulfill')

        fulfill_order.assert_not_called()


class FulfillApiTestCase(BaseTestCase):
    def setUp(self):
        self.parent_user = f.UserFactory()
        self.user = f.UserFactory()
        self.password = 'test'
        self.user.set_password(self.password)
        self.user.save()

        self.store = f.ShopifyStoreFactory(user=self.user)
        self.client.login(username=self.user.username, password=self.password)

    @tag('slow')
    def test_add_source_id(self):
        data = {
            'store': self.store.id,
            'order_id': 1000,
            'line_id': 100,
            'aliexpress_order_id': 123456789123
        }

        r = self.client.post('/api/order-fulfill', data)
        self.assertEqual(r.status_code, 200)

        self.assertEqual(ShopifyOrderTrack.objects.count(), 1)

        data.update({
            'line_id': 101,
            'aliexpress_order_id': 123456789123
        })

        r = self.client.post('/api/order-fulfill', data)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(ShopifyOrderTrack.objects.count(), 2)

    @tag('slow')
    def test_add_duplicate_source_id(self):
        data = {
            'store': self.store.id,
            'order_id': 1000,
            'line_id': 100,
            'aliexpress_order_id': 123456789123
        }

        r = self.client.post('/api/order-fulfill', data)
        self.assertEqual(r.status_code, 200)

        self.assertEqual(ShopifyOrderTrack.objects.count(), 1)

        data.update({
            'order_id': 1002,
            'line_id': 101,
            'aliexpress_order_id': 123456789123
        })

        r = self.client.post('/api/order-fulfill', data)
        self.assertEqual(r.status_code, 409)
        self.assertEqual(ShopifyOrderTrack.objects.count(), 1)

    @tag('slow')
    def test_overwrite_source_id(self):
        data = {
            'store': self.store.id,
            'order_id': 1000,
            'line_id': 100,
            'aliexpress_order_id': 123456789123
        }

        r = self.client.post('/api/order-fulfill', data)
        self.assertEqual(r.status_code, 200)

        self.assertEqual(ShopifyOrderTrack.objects.count(), 1)

        data.update({
            'order_id': 1000,
            'line_id': 100,
            'aliexpress_order_id': 123456789000
        })

        r = self.client.post('/api/order-fulfill', data)
        self.assertEqual(r.status_code, 422)
        self.assertEqual(ShopifyOrderTrack.objects.count(), 1)
