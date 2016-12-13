import simplejson as json

from django.core.cache import cache
from django.test import TestCase, TransactionTestCase
from django.contrib.auth.models import User
from django.conf import settings
from django.utils import timezone
from django.core.management import call_command

from leadgalaxy import utils
from leadgalaxy.models import (
    AliexpressProductChange,
    ShopifyOrderTrack,
    ShopifyProduct,
    ShopifyStore,
    ShopifyProductExport,
    UserProfile,
    GroupPlan
)

import factory

from mock import patch, Mock


class ShopifyOrderTrackFactory(factory.django.DjangoModelFactory):

    class Meta:
        model = ShopifyOrderTrack
        django_get_or_create = ['line_id', 'order_id', 'user_id']

    line_id = '1654811'
    order_id = '5415135175'
    source_tracking = 'MA7565915257226HK'
    user_id = 1
    store_id = 1
    status_updated_at = timezone.now()


class ShopifyStoreFactory(factory.django.DjangoModelFactory):

    class Meta:
        model = utils.ShopifyStore
        django_get_or_create = ['api_url']

    title = 'uncommonnow'
    api_url = 'https://:88937df17024aa5126203507e2147f47@shopified-app-ci.myshopify.com'
    user_id = 1
    auto_fulfill = 'enable'


class ShopifyOrderFactory(factory.django.DjangoModelFactory):

    class Meta:
        model = utils.ShopifyOrder
        django_get_or_create = ['order_id']

    order_id = '5415135175'
    country_code = 'US'
    user_id = 1
    store_id = 1
    order_number = 31
    total_price = 100
    customer_id = 1
    created_at = utils.timezone.now()
    updated_at = utils.timezone.now()


class ShopifyOrderLineFactory(factory.django.DjangoModelFactory):

    class Meta:
        model = utils.ShopifyOrderLine
        django_get_or_create = ['line_id']

    line_id = '1654811'
    shopify_product = 10000
    price = 10
    quantity = 100
    variant_id = 12345
    order = factory.SubFactory(ShopifyOrderFactory)


class AutoFulfillTestCase(TestCase):

    def setUp(self):
        self.store = ShopifyStoreFactory()

    @patch('leadgalaxy.management.commands.auto_fulfill.Command.write', Mock())
    @patch('leadgalaxy.management.commands.auto_fulfill.Command.fulfill_order')
    def test_fulfill_tracked_order(self, fulfill_order):
        track = ShopifyOrderTrackFactory(
            order_id='5415135170',
            line_id='1654810',
            source_tracking='MA7565915257226HK',
            store_id=self.store.id
        )

        track.status_updated_at = timezone.now() - timezone.timedelta(seconds=61)
        track.save()

        call_command('auto_fulfill')

        fulfill_order.assert_called_with(track)

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
