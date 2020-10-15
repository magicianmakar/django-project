import re
import random
from unittest.mock import Mock, patch, MagicMock
import json
from django.conf import settings
from django.test import tag
from redis.exceptions import LockError

from leadgalaxy.utils import aliexpress_shipping_info
from lib.test import BaseTestCase
from shopify_orders.models import ShopifyOrder, ShopifyOrderLine
from leadgalaxy import utils
from leadgalaxy.models import (
    ShopifyOrderTrack
)

from shopified_core.shipping_helper import (
    normalize_country_code,
    get_uk_province,
    valide_aliexpress_province,
    support_other_in_province,
)
from shopified_core.utils import ensure_title, hash_url_filename, get_domain, remove_link_query, random_hash

from leadgalaxy.tests.factories import UserFactory, ShopifyProductFactory, ShopifyBoardFactory

import factory
import requests


class ShopifyStoreFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = utils.ShopifyStore
        django_get_or_create = ['id']

    id = 1
    title = 'uncommonnow'
    api_url = 'https://:88937df17024aa5126203507e2147f47@shopified-app-ci.myshopify.com'
    primary_location = 1234567899
    user = factory.SubFactory('leadgalaxy.tests.factories.UserFactory')


class ShopifyOrderTrackFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ShopifyOrderTrack
        django_get_or_create = ['line_id', 'order_id', 'user']

    line_id = '1654811'
    order_id = '5415135175'
    source_tracking = 'MA7565915257226HK'
    user = factory.SubFactory('leadgalaxy.tests.factories.UserFactory')
    store = factory.SubFactory(ShopifyStoreFactory)


class ShopifyOrderFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ShopifyOrder
        django_get_or_create = ['order_id']

    order_id = '5415135175'
    country_code = 'US'
    user = factory.SubFactory('leadgalaxy.tests.factories.UserFactory')
    store = factory.SubFactory(ShopifyStoreFactory)
    order_number = 31
    total_price = 100
    customer_id = 1
    items_count = 1
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


class FulfillmentTestCase(BaseTestCase):
    def setUp(self):
        self.user = UserFactory(username='test')
        self.password = 'test'
        self.user.set_password(self.password)
        self.user.save()

        self.fulfillment_data = {
            'line_id': '123456',
            'order_id': '456789123',
            'source_tracking': 'MA7565915257226HK',
            'use_usps': True,
            'location_id': 9876543211,
            'user_config': {
                'send_shipping_confirmation': 'yes',
                'validate_tracking_number': False,
                'aftership_domain': 'track'
            }
        }

        self.store = ShopifyStoreFactory(id=1)
        self.store2 = ShopifyStoreFactory(id=2)

    def create_track(self, order_id, line_id, source_tracking, country_code):
        track = ShopifyOrderTrackFactory(order_id=order_id, line_id=line_id, source_tracking=source_tracking, store=self.store)
        order = ShopifyOrderFactory(order_id=order_id, country_code=country_code)
        ShopifyOrderLineFactory(line_id=line_id, order=order)

        return track

    def test_tracking_func(self):
        self.assertTrue(utils.is_chinese_carrier('MA7565915257226CN'))
        self.assertTrue(utils.is_chinese_carrier('MA7565915257226HK'))
        self.assertTrue(utils.is_chinese_carrier('MA7565915257226SG'))

        self.assertFalse(utils.is_chinese_carrier('7565915257226'))

        self.assertTrue(utils.is_valide_tracking_number('MA7565915257226SG'))
        self.assertTrue(utils.is_valide_tracking_number('MA7565915257226'))
        self.assertTrue(utils.is_valide_tracking_number('7565915257226SG'))
        self.assertFalse(utils.is_valide_tracking_number('7565915257226'))

    def test_fulfill_without_saved_line(self):
        track = ShopifyOrderTrackFactory(order_id='5415135170', line_id='1654810', source_tracking='MA7565915257226HK', store=self.store2)
        data = utils.order_track_fulfillment(order_track=track, user_config={})
        self.assertEqual(data['fulfillment']['tracking_company'], "Other")
        self.assertEqual(data['fulfillment']['tracking_url'], "https://track.aftership.com/{}".format(track.source_tracking))
        self.assertEqual(len(data['fulfillment']['line_items']), 1)
        self.assertEqual(data['fulfillment']['line_items'][0]['id'], '1654810')

    def test_normal_epacket_order(self):
        track = self.create_track('5415135175', '1654811', 'MA7565915257226HK', 'US')
        data = utils.order_track_fulfillment(order_track=track, user_config={})
        self.assertEqual(data['fulfillment']['tracking_company'], "USPS")
        self.assertIsNone(data['fulfillment'].get('tracking_url'))

    def test_usps_tracking_number(self):
        track = self.create_track('5415135175', '1654811', '9200190164917310525931', 'US')
        data = utils.order_track_fulfillment(order_track=track, user_config={})
        self.assertEqual(data['fulfillment']['tracking_company'], "USPS")
        self.assertIsNone(data['fulfillment'].get('tracking_url'))

    def test_fedex_tracking_number(self):
        track = self.create_track('5415135175', '1654811', '74899991206471196283', 'US')
        data = utils.order_track_fulfillment(order_track=track, user_config={})
        self.assertEqual(data['fulfillment']['tracking_company'], "FedEx")
        self.assertIsNone(data['fulfillment'].get('tracking_url'))

    def test_fedex_tracking_number2(self):
        track = self.create_track('5415135175', '1654811', '61299991206471196300', 'US')
        data = utils.order_track_fulfillment(order_track=track, user_config={})
        self.assertEqual(data['fulfillment']['tracking_company'], "FedEx")
        self.assertIsNone(data['fulfillment'].get('tracking_url'))

    def test_unrecognized_carrier(self):
        track = self.create_track('5415135176', '1654812', 'YT1614016214415424', 'US')
        data = utils.order_track_fulfillment(order_track=track, user_config={})
        self.assertEqual(data['fulfillment']['tracking_company'], "Other")
        self.assertEqual(data['fulfillment']['tracking_url'], "https://track.aftership.com/{}".format(track.source_tracking))

    def test_non_us_address(self):
        track = self.create_track('5415135177', '1654813', 'MA7565915257226HK', 'MA')
        data = utils.order_track_fulfillment(order_track=track, user_config={})
        self.assertEqual(data['fulfillment']['tracking_company'], "Other")

    def test_default_confirmation_email(self):
        track = ShopifyOrderTrackFactory(order_id='5415135170', line_id='1654810', source_tracking='MA7565915257226HK', store=self.store2)
        data = utils.order_track_fulfillment(order_track=track, user_config={})
        self.assertTrue(data['fulfillment']['notify_customer'])

        data = utils.order_track_fulfillment(order_track=track, user_config={'send_shipping_confirmation': 'default'})
        self.assertTrue(data['fulfillment']['notify_customer'])

    def test_default_confirmation_email_order_with_multi_lines_unfulfilled(self):
        order = ShopifyOrderFactory(order_id='5415135170', store=self.store2)
        lines = [
            ShopifyOrderLineFactory(order=order, line_id='1654810', fulfillment_status=''),
            ShopifyOrderLineFactory(order=order, line_id='1654811', fulfillment_status=''),
        ]

        order.items_count = order.shopifyorderline_set.count()
        order.save()

        track = ShopifyOrderTrackFactory(order_id='5415135170', line_id=lines.pop().line_id, source_tracking='MA7565915257226HK', store=self.store2)

        data = utils.order_track_fulfillment(order_track=track, user_config={'send_shipping_confirmation': 'default'})
        self.assertFalse(data['fulfillment']['notify_customer'])

    def test_default_confirmation_email_order_with_multi_lines_partialy_fulfilled(self):
        order = ShopifyOrderFactory(order_id='5415135170', store=self.store2)
        lines = [
            ShopifyOrderLineFactory(order=order, line_id='1654810', fulfillment_status='fulfilled'),
            ShopifyOrderLineFactory(order=order, line_id='1654811', fulfillment_status=''),
        ]

        order.items_count = order.shopifyorderline_set.count()
        order.save()

        track = ShopifyOrderTrackFactory(order_id='5415135170', line_id=lines.pop().line_id, source_tracking='MA7565915257226HK', store=self.store2)

        data = utils.order_track_fulfillment(order_track=track, user_config={'send_shipping_confirmation': 'default'})
        self.assertTrue(data['fulfillment']['notify_customer'])

    def test_default_confirmation_email_order_with_multi_lines_already_fulfilled(self):
        order = ShopifyOrderFactory(order_id='5415135170', store=self.store2)
        lines = [
            ShopifyOrderLineFactory(order=order, line_id='1654810', fulfillment_status='fulfilled'),
            ShopifyOrderLineFactory(order=order, line_id='1654811', fulfillment_status='fulfilled'),
        ]

        order.items_count = order.shopifyorderline_set.count()
        order.save()

        track = ShopifyOrderTrackFactory(order_id='5415135170', line_id=lines.pop().line_id, source_tracking='MA7565915257226HK', store=self.store2)

        data = utils.order_track_fulfillment(order_track=track, user_config={'send_shipping_confirmation': 'default'})
        self.assertTrue(data['fulfillment']['notify_customer'])

    def test_default_confirmation_email_order_with_multi_lines_partialy_fulfilled_duplicated(self):
        order = ShopifyOrderFactory(order_id='5415135170', store=self.store2)
        lines = [
            ShopifyOrderLineFactory(order=order, line_id='1654810', fulfillment_status='fulfilled'),
            ShopifyOrderLineFactory(order=order, line_id='1654811', fulfillment_status=''),
        ]

        order.items_count = order.shopifyorderline_set.count()
        order.save()

        track = ShopifyOrderTrackFactory(order_id='5415135170', line_id=lines[0].line_id, source_tracking='MA7565915257226HK', store=self.store2)

        data = utils.order_track_fulfillment(order_track=track, user_config={'send_shipping_confirmation': 'default'})
        self.assertFalse(data['fulfillment']['notify_customer'])

    def test_default_confirmation_email_order_with_multi_lines_all(self):
        order = ShopifyOrderFactory(order_id='5415135170', store=self.store2)
        lines = [
            ShopifyOrderLineFactory(order=order, line_id='1654810', fulfillment_status=''),
            ShopifyOrderLineFactory(order=order, line_id='1654811', fulfillment_status=''),
            ShopifyOrderLineFactory(order=order, line_id='1654812', fulfillment_status=''),
        ]

        order.items_count = order.shopifyorderline_set.count()
        order.save()

        for i, line in enumerate(lines):
            track = ShopifyOrderTrackFactory(order_id='5415135170', line_id=line.line_id, source_tracking='MA7565915257226HK', store=self.store2)
            data = utils.order_track_fulfillment(order_track=track, user_config={'send_shipping_confirmation': 'default'})

            # notify_customer should be True for last line only
            self.assertEqual(data['fulfillment']['notify_customer'], len(lines) - 1 == i)

    def test_dont_send_confirmation_email(self):
        track = ShopifyOrderTrackFactory(order_id='5415135170', line_id='1654810', source_tracking='MA7565915257226HK', store=self.store2)
        data = utils.order_track_fulfillment(order_track=track, user_config={'send_shipping_confirmation': 'no'})
        self.assertFalse(data['fulfillment']['notify_customer'])

    def test_always_send_confirmation_email(self):
        track = ShopifyOrderTrackFactory(order_id='5415135170', line_id='1654810', source_tracking='MA7565915257226HK', store=self.store2)
        data = utils.order_track_fulfillment(order_track=track, user_config={'send_shipping_confirmation': 'yes'})
        self.assertTrue(data['fulfillment']['notify_customer'])

    def test_always_send_confirmation_email_if_tracking_is_valid(self):
        track = ShopifyOrderTrackFactory(order_id='5415135170', line_id='1654810', source_tracking='MA7565915257226HK', store=self.store2)
        data = utils.order_track_fulfillment(order_track=track, user_config={'send_shipping_confirmation': 'yes', 'validate_tracking_number': True})
        self.assertTrue(data['fulfillment']['notify_customer'])

        track2 = self.create_track('5415135176', '1654814', '7565915257226', 'MA')
        data = utils.order_track_fulfillment(order_track=track2, user_config={'send_shipping_confirmation': 'yes', 'validate_tracking_number': True})
        self.assertFalse(data['fulfillment']['notify_customer'])

        track3 = self.create_track('5415135176', '1654815', '74899991206471196283', 'MA')
        data = utils.order_track_fulfillment(order_track=track3, user_config={'send_shipping_confirmation': 'yes', 'validate_tracking_number': True})
        self.assertTrue(data['fulfillment']['notify_customer'])

    def test_custom_aftership_domain(self):
        track = ShopifyOrderTrackFactory(order_id='5415135170', line_id='1654810', source_tracking='MA7565915257226HK', store=self.store2)
        data = utils.order_track_fulfillment(order_track=track, user_config={'aftership_domain': {"2": 'uncommonnow'}})
        self.assertEqual(data['fulfillment']['tracking_url'], "https://uncommonnow.aftership.com/{}".format(track.source_tracking))

    def test_custom_aftership_domain_with_us_epacket(self):
        # User have a custom tracking, it should be used even for ePacket-US instead of USPS
        track = self.create_track('5415135175', '1654811', 'MA7565915257226HK', 'US')
        data = utils.order_track_fulfillment(order_track=track, user_config={'aftership_domain': {"1": 'uncommonnow'}})
        self.assertEqual(data['fulfillment']['tracking_company'], "Other")
        self.assertEqual(data['fulfillment']['tracking_url'], "https://uncommonnow.aftership.com/{}".format(track.source_tracking))

    def test_other_store_have_custom_aftership_domain_with_us_epacket(self):
        # User have a custom tracking, it should be used even for ePacket-US instead of USPS
        track = self.create_track('5415135175', '1654811', 'MA7565915257226HK', 'US')
        data = utils.order_track_fulfillment(order_track=track, user_config={'aftership_domain': {"2": 'uncommonnow'}})
        self.assertEqual(data['fulfillment']['tracking_company'], "USPS")
        self.assertIsNone(data['fulfillment'].get('tracking_url'))

    def test_multi_tracking_numbers(self):
        # User have a custom tracking, it should be used even for ePacket-US instead of USPS
        track = self.create_track('5415135175', '1654811', 'MA7565915257226HK,MA7565915257227HK', 'US')
        data = utils.order_track_fulfillment(order_track=track, user_config={})
        self.assertNotIn('tracking_number', data['fulfillment'])
        self.assertNotIn('tracking_urls', data['fulfillment'])

        self.assertEqual(data['fulfillment']['tracking_numbers'], ["MA7565915257226HK", "MA7565915257227HK"])
        self.assertEqual(data['fulfillment']['tracking_company'], "USPS")

    def test_muti_tracking_numbers_with_custom_urls(self):
        # User have a custom tracking, it should be used even for ePacket-US instead of USPS
        track = self.create_track('5415135175', '1654811', 'MA7565915257226HK,MA7565915257227HK', 'US')
        data = utils.order_track_fulfillment(order_track=track, user_config={'aftership_domain': {"1": 'uncommonnow'}})
        self.assertEqual(data['fulfillment']['tracking_numbers'], ["MA7565915257226HK", "MA7565915257227HK"])
        self.assertEqual(data['fulfillment']['tracking_company'], "Other")
        self.assertEqual(data['fulfillment']['tracking_urls'],
                         ['https://uncommonnow.aftership.com/MA7565915257226HK', 'https://uncommonnow.aftership.com/MA7565915257227HK'])

        self.assertNotIn('tracking_url', data['fulfillment'])
        self.assertNotIn('tracking_number', data['fulfillment'])

    def test_manual_fulfilement(self):
        data = utils.order_track_fulfillment(**self.fulfillment_data)
        self.assertEqual(data['fulfillment']['tracking_company'], "USPS")
        self.assertIsNone(data['fulfillment'].get('tracking_url'))
        self.assertTrue(data['fulfillment']['notify_customer'])

    def test_manual_fulfilement_empty_tracking(self):
        # Empty Tracking
        self.fulfillment_data['source_tracking'] = ''
        data = utils.order_track_fulfillment(**self.fulfillment_data)
        self.assertIsNone(data['fulfillment']['tracking_number'])
        self.assertNotIn('tracking_url', data['fulfillment'])
        self.assertNotIn('tracking_company', data['fulfillment'])

    def test_manual_fulfilement_aftership(self):
        # Aftership tracking
        self.fulfillment_data['source_tracking'] = 'MA7565915257226HK'
        self.fulfillment_data['use_usps'] = False
        data = utils.order_track_fulfillment(**self.fulfillment_data)
        self.assertEqual(data['fulfillment']['tracking_company'], "Other")
        self.assertEqual(data['fulfillment']['tracking_url'], "https://track.aftership.com/{}".format(self.fulfillment_data['source_tracking']))

    def test_manual_fulfilement_aftership_custom(self):
        # Custom Aftership domain
        self.fulfillment_data['source_tracking'] = 'MA7565915257226HK'
        self.fulfillment_data['use_usps'] = False
        self.fulfillment_data['store_id'] = 2
        self.fulfillment_data['user_config']['aftership_domain'] = {"2": "uncommonnow"}
        data = utils.order_track_fulfillment(**self.fulfillment_data)
        self.assertEqual(data['fulfillment']['tracking_url'], "https://uncommonnow.aftership.com/{}".format(self.fulfillment_data['source_tracking']))

    def test_manual_fulfilement_aftership_custom_even_usps(self):
        # User have a Custom Aftership domain and this is a ePacket-US order but he didn't choose USPS
        self.create_track('54151351750', '16548110', 'MA7565915257226HK', 'US')

        self.fulfillment_data['order_id'] = '54151351750'
        self.fulfillment_data['line_id'] = '16548110'
        self.fulfillment_data['source_tracking'] = 'MA7565915257226HK'
        self.fulfillment_data['store_id'] = 2
        self.fulfillment_data['user_config']['aftership_domain'] = {"2": "uncommonnow"}
        del self.fulfillment_data['use_usps']

        data = utils.order_track_fulfillment(**self.fulfillment_data)
        self.assertEqual(data['fulfillment']['tracking_url'], "https://uncommonnow.aftership.com/{}".format(self.fulfillment_data['source_tracking']))

    def test_manual_fulfilement_aftership_custom_force_usps(self):
        # User have a Custom Aftership domain but choose USPS from the dialog for an ePacket-US order
        self.create_track('54151351750', '16548110', 'MA7565915257226HK', 'US')

        self.fulfillment_data['order_id'] = '54151351750'
        self.fulfillment_data['line_id'] = '16548110'
        self.fulfillment_data['source_tracking'] = 'MA7565915257226HK'
        self.fulfillment_data['store_id'] = 2
        self.fulfillment_data['user_config']['aftership_domain'] = {"2": "uncommonnow"}
        self.fulfillment_data['use_usps'] = True

        data = utils.order_track_fulfillment(**self.fulfillment_data)
        self.assertEqual(data['fulfillment']['tracking_company'], "USPS")
        self.assertIsNone(data['fulfillment'].get('tracking_url'))

    def test_manual_fulfilement_aftership_custom_url(self):
        # Custom Aftership domain
        self.fulfillment_data['source_tracking'] = 'MA7565915257226HK'
        self.fulfillment_data['use_usps'] = False
        self.fulfillment_data['store_id'] = 2
        self.fulfillment_data['user_config']['aftership_domain'] = {"2": "https://track.uncommonnow.com/{{tracking_number}}"}
        data = utils.order_track_fulfillment(**self.fulfillment_data)
        self.assertEqual(data['fulfillment']['tracking_url'], "https://track.uncommonnow.com/{}".format(self.fulfillment_data['source_tracking']))

    def test_manual_fulfilement_aftership_custom_url2(self):
        # Custom Aftership domain
        self.fulfillment_data['source_tracking'] = 'MA7565915257226HK'
        self.fulfillment_data['use_usps'] = False
        self.fulfillment_data['store_id'] = 2
        self.fulfillment_data['user_config']['aftership_domain'] = {"2": "https://www.google.co.in/#q={{tracking_number}}"}
        data = utils.order_track_fulfillment(**self.fulfillment_data)
        self.assertEqual(data['fulfillment']['tracking_url'], "https://www.google.co.in/#q={}".format(self.fulfillment_data['source_tracking']))

    def test_manual_fulfilement_aftership_custom_url_fix(self):
        # Custom Aftership domain
        self.fulfillment_data['source_tracking'] = 'MA7565915257226HK'
        self.fulfillment_data['use_usps'] = False
        self.fulfillment_data['store_id'] = 2
        self.fulfillment_data['user_config']['aftership_domain'] = {"2": "track.uncommonnow.com/{{tracking_number}}"}
        data = utils.order_track_fulfillment(**self.fulfillment_data)
        self.assertEqual(data['fulfillment']['tracking_url'], "https://track.uncommonnow.com/{}".format(self.fulfillment_data['source_tracking']))

    def test_manual_fulfilement_aftership_custom_url_fix_scheme(self):
        # Custom Aftership domain
        self.fulfillment_data['source_tracking'] = 'MA7565915257226HK'
        self.fulfillment_data['use_usps'] = False
        self.fulfillment_data['store_id'] = 2
        self.fulfillment_data['user_config']['aftership_domain'] = {"2": "//track.uncommonnow.com/{{tracking_number}}"}
        data = utils.order_track_fulfillment(**self.fulfillment_data)
        self.assertEqual(data['fulfillment']['tracking_url'], "https://track.uncommonnow.com/{}".format(self.fulfillment_data['source_tracking']))

    def test_manual_fulfilement_empty_track_with_shopifyorder(self):
        # Empty Tracking with ShopifyOrder
        self.create_track('456789321', '789456', '', 'US')

        self.fulfillment_data['source_tracking'] = ''
        self.fulfillment_data['order_id'] = '456789321'
        self.fulfillment_data['line_id'] = '789456'
        data = utils.order_track_fulfillment(**self.fulfillment_data)
        self.assertIsNone(data['fulfillment']['tracking_number'])

    def test_manual_fulfilement_no_usps_with_shopifyorder(self):
        # Assert to not use USPS for Tracking with ShopifyOrder
        self.create_track('456789321', '789456', 'MA7565915257226HK', 'US')

        self.fulfillment_data['source_tracking'] = 'MA7565915257226HK'
        self.fulfillment_data['order_id'] = '456789321'
        self.fulfillment_data['line_id'] = '789456'
        self.fulfillment_data['use_usps'] = False
        data = utils.order_track_fulfillment(**self.fulfillment_data)
        self.assertEqual(data['fulfillment']['tracking_company'], "Other")

    def test_manual_fulfilement_force_usps(self):
        # Force USPS use
        self.fulfillment_data['use_usps'] = True
        data = utils.order_track_fulfillment(**self.fulfillment_data)
        self.assertEqual(data['fulfillment']['tracking_company'], "USPS")

    def test_manual_fulfilement_force_usps_nonvalid_track(self):
        # Force USPS use for non valid tracking
        self.create_track('4567893477', '78945611', '7565915257226', 'MA')
        self.fulfillment_data['order_id'] = '4567893477'
        self.fulfillment_data['line_id'] = '78945611'
        self.fulfillment_data['use_usps'] = True
        data = utils.order_track_fulfillment(**self.fulfillment_data)
        self.assertEqual(data['fulfillment']['tracking_company'], "USPS")

    def test_order_track_urls_single(self):
        track = self.create_track('4567893477', '78945611', '7565915257226', 'MA')
        r = track.get_tracking_link()

        self.assertEqual(type(r), str)
        self.assertEqual(r, 'https://track.aftership.com/7565915257226')

    def test_order_track_urls_multi(self):
        track = self.create_track('4567893477', '78945611', '7565915257226,7565915257227', 'MA')
        r = track.get_tracking_link()

        self.assertEqual(type(r), list)
        self.assertEqual(r, [['7565915257226', 'https://track.aftership.com/7565915257226'],
                             ['7565915257227', 'https://track.aftership.com/7565915257227']])


class OrdersTestCase(BaseTestCase):
    def setUp(self):
        pass

    @tag('slow', 'excessive')
    def test_order_notes(self):
        order_id = 4905209738
        line_id = 9309669834

        store = ShopifyStoreFactory()
        order = utils.get_shopify_order(store, order_id)
        self.assertEqual(order['id'], order_id)

        note1 = 'Test Note #%s' % random_hash()
        utils.set_shopify_order_note(store, order_id, note1)

        self.assertEqual(note1, utils.get_shopify_order_note(store, order_id))

        note2 = 'An other Test Note #%s' % random_hash()
        utils.add_shopify_order_note(store, order_id, note2)

        order_note = utils.get_shopify_order_note(store, order_id)
        self.assertIn(note1, order_note)
        self.assertIn(note2, order_note)

        line = utils.get_shopify_order_line(store, order_id, line_id)
        self.assertEqual(line['id'], line_id)

        line, current_note = utils.get_shopify_order_line(store, order_id, line_id, note=True)
        self.assertEqual(line['id'], line_id)
        self.assertIsNotNone(current_note)

        note3 = 'Yet An other Test Note #%s' % random_hash()
        utils.add_shopify_order_note(store, order_id, note3, current_note=current_note)

        order_note = utils.get_shopify_order_note(store, order_id)

        self.assertIn(note1, order_note)
        self.assertIn(note2, order_note)
        self.assertIn(note3, order_note)

        utils.set_shopify_order_note(store, order_id, '')

    @tag('slow', 'excessive')
    def test_order_updater_note(self):
        store = ShopifyStoreFactory()
        order_id = 579111223384

        note = 'Test Note #%s' % random_hash()

        updater = utils.ShopifyOrderUpdater(store, order_id)
        updater.add_note(note)

        updater.reset('notes')

        try:
            updater.save_changes()
            self.assertEqual(note, utils.get_shopify_order_note(store, order_id))
        except LockError:
            pass

    @tag('slow', 'excessive')
    def test_order_updater_note_unicode(self):
        store = ShopifyStoreFactory()
        order_id = 579111518296

        feed = requests.get('http://feeds.bbci.co.uk/japanese/rss.xml')
        if not feed.ok:
            return

        unicode_text = random.choice([i[1] for i in re.findall(r'title>(<!\[CDATA\[)([^>]+)(]]>)</title', feed.text)])

        utils.set_shopify_order_note(store, order_id, unicode_text)

        note = 'Test Note #%s' % random_hash()

        updater = utils.ShopifyOrderUpdater(store, order_id)
        updater.add_note(note)
        try:
            updater.save_changes()
        except LockError:
            return

        current_note = utils.get_shopify_order_note(store, order_id)

        self.assertIn(unicode_text, current_note)
        self.assertIn(note, current_note)

        updater.reset('notes')

    @tag('slow', 'excessive')
    def test_order_updater_tags(self):
        store = ShopifyStoreFactory()
        order_id = 579111714904

        tag = '#%s' % random_hash()

        updater = utils.ShopifyOrderUpdater(store, order_id)
        updater.add_tag(tag)

        updater.reset('tags')

        try:
            updater.save_changes()
        except LockError:
            return

        self.assertEqual(tag, utils.get_shopify_order(store, order_id)['tags'])

    @tag('slow', 'excessive')
    def test_order_updater_attributes(self):
        store = ShopifyStoreFactory()
        order_id = 579111845976

        attrib = {'name': random_hash(), 'value': random_hash()}

        updater = utils.ShopifyOrderUpdater(store, order_id)
        updater.add_attribute(attrib)

        updater.reset('attributes')

        try:
            updater.save_changes()
        except LockError:
            return

        self.assertEqual([attrib], utils.get_shopify_order(store, order_id)['note_attributes'])

    def test_order_updater_have_changes_attributes(self):
        updater = utils.ShopifyOrderUpdater(ShopifyStoreFactory(), 579431268440)
        self.assertFalse(updater.have_changes())

        updater.add_attribute({'name': random_hash(), 'value': random_hash()})
        self.assertTrue(updater.have_changes())

    def test_order_updater_have_changes_tags(self):
        updater = utils.ShopifyOrderUpdater(ShopifyStoreFactory(), 579431661656)
        self.assertFalse(updater.have_changes())

        updater.add_tag('tag')
        self.assertTrue(updater.have_changes())

    def test_order_updater_have_changes_notes(self):
        updater = utils.ShopifyOrderUpdater(ShopifyStoreFactory(), 579432153176)
        self.assertFalse(updater.have_changes())

        updater.add_note('note')
        self.assertTrue(updater.have_changes())

    def test_order_updater_have_changes_all(self):
        updater = utils.ShopifyOrderUpdater(ShopifyStoreFactory(), 579432546392)
        self.assertFalse(updater.have_changes())

        updater.add_tag('tag')
        updater.add_note('note')
        updater.add_attribute({'name': random_hash(), 'value': random_hash()})

        self.assertTrue(updater.have_changes())


class UtilsTestCase(BaseTestCase):
    def setUp(self):
        pass

    def test_get_domain(self):
        self.assertEqual(get_domain('www.aliexpress.com'), 'aliexpress')
        self.assertEqual(get_domain('http://www.aliexpress.com'), 'aliexpress')
        self.assertEqual(get_domain('www.aliexpress.com/item/UNO-R3/32213964945.html'), 'aliexpress')
        self.assertEqual(get_domain('http://www.aliexpress.com/item/UNO-R3/32213964945.html'), 'aliexpress')
        self.assertEqual(get_domain('http://s.aliexpress.com/seeplink.html?id=32213964945'), 'aliexpress')
        self.assertEqual(get_domain('www.ebay.com/itm/131696353919'), 'ebay')
        self.assertEqual(get_domain('http://www.ebay.com/itm/131696353919'), 'ebay')
        self.assertEqual(get_domain('www.amazon.co.uk'), 'amazon')
        self.assertEqual(get_domain('www.amazon.fr'), 'amazon')
        self.assertEqual(get_domain('www.amazon.de'), 'amazon')
        self.assertEqual(get_domain('www.wanelo.co'), 'wanelo')
        self.assertEqual(get_domain('http://www.costco.com/Jura.product.100223622.html'), 'costco')
        self.assertEqual(get_domain('http://www.qvc.com/egiftcards'), 'qvc')
        self.assertEqual(get_domain('http://shopified-app-ci.myshopify.com/admin/products/1234'), 'myshopify')

        self.assertEqual(get_domain('www.aliexpress.com', full=True), 'www.aliexpress.com')
        self.assertEqual(get_domain('http://www.aliexpress.com/item/UNO-R3/32213964945.html', full=True), 'www.aliexpress.com')
        self.assertEqual(get_domain('http://aliexpress.com/item/UNO-R3/32213964945.html', full=True), 'aliexpress.com')
        self.assertEqual(get_domain('http://www.ebay.com/itm/131696353919', full=True), 'www.ebay.com')
        self.assertEqual(get_domain('http://shopified-app-ci.myshopify.com/admin/products/1234', full=True), 'shopified-app-ci.myshopify.com')

    def test_remove_link_query(self):
        self.assertEqual(
            remove_link_query('https://cdn.shopify.com/s/files/1/1013/1174/products/Fashion-Metal---magnification-wholesale.jpeg?v=1452639314'),
            'https://cdn.shopify.com/s/files/1/1013/1174/products/Fashion-Metal---magnification-wholesale.jpeg')

        self.assertEqual(
            remove_link_query('http://www.ebay.com/itm/131696353919?v=1452639314'),
            'http://www.ebay.com/itm/131696353919')

        self.assertEqual(
            remove_link_query('http://www.ebay.com/itm/131696353919#hash:12'),
            'http://www.ebay.com/itm/131696353919')

        self.assertEqual(
            remove_link_query('https://i.ebayimg.com/images/g/RHIAAOSwQaJXRBkE/s-l500.jpg?hash=1e56ace2'),
            'https://i.ebayimg.com/images/g/RHIAAOSwQaJXRBkE/s-l500.jpg')

        self.assertEqual(
            remove_link_query('http://www.ebay.com/itm/131696353919?v=1452639314#hash:12'),
            'http://www.ebay.com/itm/131696353919')

        self.assertEqual(
            remove_link_query('http://g03.a.alicdn.com/kf/HTB13OOBLFXXXXcoXpXXq6xXFXXXp/Vente-chaude-vinyle-amovible-stickers-muraux-t&ecirc;te-de-cheval-peintures-murales-salon-d&eacute;corative-animaux-accueil-autocollant.jpg'), # noqa
            'http://g03.a.alicdn.com/kf/HTB13OOBLFXXXXcoXpXXq6xXFXXXp/Vente-chaude-vinyle-amovible-stickers-muraux-t&ecirc;te-de-cheval-peintures-murales-salon-d&eacute;corative-animaux-accueil-autocollant.jpg') # noqa

        self.assertEqual(
            remove_link_query('www.aliexpress.com/store/1185416?spm=2114.10010108.0.627.LN13ZN'),
            'http://www.aliexpress.com/store/1185416')

        self.assertEqual(
            remove_link_query('http://www.ebay.com/itm/131696353919?'),
            'http://www.ebay.com/itm/131696353919')

        self.assertEqual(
            remove_link_query('http://www.ebay.com/itm/131696353919'),
            'http://www.ebay.com/itm/131696353919')

        self.assertEqual(
            remove_link_query('//www.ebay.com/itm/131696353919'),
            'http://www.ebay.com/itm/131696353919')

        self.assertEqual(
            remove_link_query('://www.ebay.com/itm/131696353919'),
            'http://www.ebay.com/itm/131696353919')

    def test_upload_from_url(self):
        aviary_url = ('://s3.amazonaws.com/feather-files-aviary-prod-us-east-1',
                      '/220489e3e16f4691bc88d1ef81e05a8b/2016-05-24/00b4838ae29840d1bcfa6d2fa570ab02.png')

        self.assertTrue(utils.upload_from_url('http' + ''.join(aviary_url)))
        self.assertTrue(utils.upload_from_url('https' + ''.join(aviary_url)))

        self.assertTrue(utils.upload_from_url('http://i.ebayimg.com/images/g/RHIAAOSwQaJXRBkE/s-l500.jpg'))
        self.assertTrue(utils.upload_from_url('http://shopifiedapp.s3.amazonaws.com/uploads/u1/d3d1aed3576999dca762cad33b31c79a.png'))
        self.assertTrue(utils.upload_from_url('http://%s.s3.amazonaws.com/uploads/u1/d3d1aed3576999dca762cad33b31c79a.png' % settings.S3_UPLOADS_BUCKET)) # noqa
        self.assertTrue(utils.upload_from_url('http://%s.s3.amazonaws.com/uploads/u1/d3d1aed3576999dca762cad33b31c79a.png' % settings.S3_STATIC_BUCKET)) # noqa
        self.assertTrue(utils.upload_from_url('http://d2kadg5e284yn4.cloudfront.net/uploads/u1/d3d1aed3576999dca762cad33b31c79a.png'))
        self.assertTrue(utils.upload_from_url('http://cdn.dropified.com/uploads/u1/d3d1aed3576999dca762cad33b31c79a.png'))
        self.assertTrue(utils.upload_from_url('https://betaimages.sunfrogshirts.com/m_1349black.jpg'))
        self.assertTrue(utils.upload_from_url('https://cdn.shopify.com/s/files/1/1013/1174/products/Fashion-Metal---magnification-wholesale.jpeg'))
        self.assertTrue(utils.upload_from_url('https://cdn.shopify.com/s/files/1/1013/1174/products/Fashion-Metal---magnification-wholesale.jpeg?v=1452639314')) # noqa
        self.assertTrue(utils.upload_from_url('http://ecx.images-amazon.com/images/I/21iTIaYnSzL.jpg'))
        self.assertTrue(utils.upload_from_url('http://www.dhresource.com/0x0/f2/albu/g2/M00/DF/F1/rBVaGlUVIdWAIH4VAASbr7-6PiQ259.jpg'))
        self.assertTrue(utils.upload_from_url('http://i00.i.aliimg.com/img/pb/848/720/003/1003720848_179.jpg'))
        self.assertTrue(utils.upload_from_url('https://images-na.ssl-images-amazon.com/images/I/31JWz%%2BtzxSL.jpg'))
        self.assertTrue(utils.upload_from_url('https://s3.amazonaws.com/feather-client-files-aviary-prod-us-east-1/'
                                              '2016-06-16/567cc9301bc243ef91f763ce69c18f19.jpg'))

        self.assertTrue(utils.upload_from_url('http://gloimg.sammydress.com/S/pdm-product-pic/Clothing/'
                                              '2016/04/08/source-img/20160408155854_48756.jpg',
                                              stores=['sammydress']))

        self.assertFalse(utils.upload_from_url('http://gloimg.sammydress.com/S/pdm-product-pic/Clothing/'
                                               '2016/04/08/source-img/20160408155854_48756.jpg',
                                               stores=[]))

        self.assertFalse(utils.upload_from_url('http://attaker.s3.amazonaws.com/uploads/9400627bb3e695bf96eda56a3172e1bf.png'))

        # Mimetype checks
        self.assertFalse(utils.upload_from_url('http://i.ebayimg.com/files/g/RHIAAOSwQaJXRBkE/test.zip'))
        self.assertFalse(utils.upload_from_url('http://i.ebayimg.com/files/g/RHIAAOSwQaJXRBkE/test.zip?test.png'))
        self.assertFalse(utils.upload_from_url('http://attaker.com/files/g/RHIAAOSwQaJXRBkE/test.png'))
        self.assertFalse(utils.upload_from_url('http://attaker.com/files/g/RHIAAOSwQaJXRBkE/http%s/test.png' % aviary_url[0]))

    def test_get_shopify_id(self):
        self.assertEqual(utils.get_shopify_id('https://shopified-app-ci.myshopify.com/admin/products/5321947333'), 5321947333)
        self.assertEqual(utils.get_shopify_id('https://shopified-app-ci.myshopify.com/admin/products/5321947333/variants/16557264133'), 5321947333)
        self.assertEqual(utils.get_shopify_id('https://shopified-app-ci.myshopify.com/admin/products/'), 0)
        self.assertEqual(utils.get_shopify_id(None), 0)

    def test_get_shopify_store_by_url(self):
        user = utils.User.objects.create_user(username='john', email='john.test@gmail.com', password='123456')
        store = ShopifyStoreFactory(user_id=user.id)

        url = 'http://shopified-app-ci.myshopify.com/admin/products/1234'

        self.assertEqual(utils.get_store_from_url(user, url), store)

        url = 'http://notfound.myshopify.com/admin/products/1234'
        self.assertIsNone(utils.get_store_from_url(user, url))

    def test_ensure_title_word(self):
        self.assertEqual(ensure_title('james'), 'James')
        self.assertEqual(ensure_title('James'), 'James')
        self.assertEqual(ensure_title('JAMES'), 'JAMES')

    def test_ensure_title_str(self):
        self.assertEqual(ensure_title('james bond'), 'James Bond')

    def test_ensure_title_unicode(self):
        self.assertEqual(ensure_title('vari\xe9t\xe9'), 'Vari\xe9t\xe9')

    def test_aliexpress_shipping_method(self):
        data = aliexpress_shipping_info(4000869234210, "US")
        self.assertTrue(data)
        self.assertIn('freight', data)
        self.assertEqual(len(data['freight']), 4)

        for k in ['price', 'companyDisplayName', 'company', 'time', 'isTracked']:
            self.assertIn(k, data['freight'][0])


class CustomerAddressTestCase(BaseTestCase):
    def test_german_umlauts(self):
        order = {
            'shipping_address': {
                "last_name": "Smith",
                "first_name": "Kamal",
                "city": "Rabat",
                "province": "Alaska",
                "zip": "95500",
                "name": "Kamal Smith",
                "address2": "",
                "country": "United States",
                "province_code": "AK",
                "phone": "123456789",
                "country_code": "US",
                "company": "",
                "address1": "5th Ave üop",
            }
        }

        order, addr = utils.shopify_customer_address(order)
        self.assertEqual(addr['address1'], '5th Ave uop')

        order, addr = utils.shopify_customer_address(order, german_umlauts=True)
        self.assertEqual(addr['address1'], '5th Ave ueop')

        vals = {
            "5TH AVE ÜOP": '5TH AVE UEOP',
            "5th Ave äop": '5th Ave aeop',
            "5TH AVE ÄOP": '5TH AVE AEOP',
            "5th Ave öop": '5th Ave oeop',
            "5TH AVE ÖOP": '5TH AVE OEOP',
        }

        for k, v in list(vals.items()):
            order['shipping_address']['address1'] = k
            order, addr = utils.shopify_customer_address(order, german_umlauts=True)
            self.assertEqual(addr['address1'], v)


class ShippingHelperTestCase(BaseTestCase):
    def get_order(self, **kwargs):
        shipping_address = {
            "country_code": "US",
            "country": "United States",

            "province": "Alaska",
            "city": "Akiak",
            "zip": "75019",

            "address1": "Allee Anne-de-Beaujeu N365",
            "address2": "",

            "first_name": "Anna",
            "last_name": "Smith",
            "name": "Anna Smith",
            "province_code": None,  # Not used
            "phone": "85549863",
            "company": ""
        }

        shipping_address.update(kwargs)

        return {'shipping_address': shipping_address}

    def test_normalize_country_code(self):
        for country in ['uk', 'gb', 'united kingdom']:
            self.assertEqual('uk', normalize_country_code(country))

        for country in ['es', 'spain']:
            self.assertEqual('es', normalize_country_code(country))

        for country in ['au', 'australia']:
            self.assertEqual('au', normalize_country_code(country))

        for country in ['nl', 'netherlands']:
            self.assertEqual('nl', normalize_country_code(country))

        for country in ['cl', 'chile']:
            self.assertEqual('cl', normalize_country_code(country))

        for country in ['ua', 'ukraine']:
            self.assertEqual('ua', normalize_country_code(country))

        for country in ['nz', 'new zealand']:
            self.assertEqual('nz', normalize_country_code(country))

        for country in ['us', 'united states']:
            self.assertEqual('us', normalize_country_code(country))

        for country in ['ca', 'canada']:
            self.assertEqual('ca', normalize_country_code(country))

        for country in ['ru', 'russia']:
            self.assertEqual('ru', normalize_country_code(country))

        for country in ['id', 'indonesia']:
            self.assertEqual('id', normalize_country_code(country))

        for country in ['th', 'thailand']:
            self.assertEqual('th', normalize_country_code(country))

        for country in ['pl', 'poland']:
            self.assertEqual('pl', normalize_country_code(country))

        for country in ['fr', 'france']:
            self.assertEqual('fr', normalize_country_code(country))

        for country in ['it', 'italy']:
            self.assertEqual('it', normalize_country_code(country))

        for country in ['tr', 'turkey']:
            self.assertEqual('tr', normalize_country_code(country))

        for country in ['br', 'brazil']:
            self.assertEqual('br', normalize_country_code(country))

        for country in ['kr', 'korea', 'south korea']:
            self.assertEqual('kr', normalize_country_code(country))

        for country in ['sa', 'saudi arabia']:
            self.assertEqual('sa', normalize_country_code(country))

    def test_uk_validate_address(self):
        valide, correction = valide_aliexpress_province('uk', 'england', 'Kent')
        self.assertTrue(valide)

        valide, correction = valide_aliexpress_province('uk', 'Anguilla', 'NotFound')
        self.assertTrue(valide)

        valide, correction = valide_aliexpress_province('uk', 'england', 'NotFound')
        self.assertFalse(valide)

        valide, correction = valide_aliexpress_province('uk', 'NotFound', 'Kent')
        self.assertFalse(valide)

    def test_uk_fix_address(self):
        self.assertEqual(get_uk_province('Kent'), 'England')
        self.assertEqual(get_uk_province('Avon'), 'Other')

    def test_auto_city_fix_uk(self):
        valide, correction = valide_aliexpress_province('UK', 'england', 'Kent', auto_correct=True)
        self.assertTrue(valide)

        valide, correction = valide_aliexpress_province('UK', 'england', 'Knt', auto_correct=True)
        self.assertFalse(valide)

        valide, correction = valide_aliexpress_province('UK', 'england', 'Kentt', auto_correct=True)
        self.assertFalse(valide)

        valide, correction = valide_aliexpress_province('UK', 'england', 'kentt', auto_correct=True)
        self.assertFalse(valide)

        valide, correction = valide_aliexpress_province('UK', 'Isle-Of-Man', 'Random', auto_correct=True)
        self.assertEqual(correction['province'], 'Isle of Man')
        self.assertTrue(valide)

        valide, correction = valide_aliexpress_province('UK', 'isle-of-man', 'random', auto_correct=True)
        self.assertEqual(correction['province'], 'Isle of Man')
        self.assertTrue(valide)

        valide, correction = valide_aliexpress_province('united Kingdom', 'england', 'Krtt', auto_correct=True)
        self.assertFalse(valide)

        valide, correction = valide_aliexpress_province('united Kingdom', 'eng-land', 'Krtt', auto_correct=True)
        self.assertEqual(correction['province'], 'England')
        self.assertFalse(valide)

        valide, correction = valide_aliexpress_province('united Kingdom', 'eng-land', 'blackpol', auto_correct=True)
        self.assertEqual(correction['province'], 'England')
        self.assertEqual(correction['city'], 'Blackpool')
        self.assertTrue(valide)

        valide, correction = valide_aliexpress_province('united Kingdom', 'Englaand', 'city f Bristol', auto_correct=True)
        self.assertEqual(correction['province'], 'England')
        self.assertEqual(correction['city'], 'City of Bristol')
        self.assertTrue(valide)

        valide, correction = valide_aliexpress_province('united Kingdom', 'England', 'Northhampton', auto_correct=True)
        self.assertEqual(len(correction), 0)
        self.assertFalse(valide)

        valide, correction = valide_aliexpress_province('united Kingdom', 'England', 'Washington', auto_correct=True)
        self.assertEqual(len(correction), 0)
        self.assertFalse(valide)

    def test_auto_city_fix_us(self):
        valide, correction = valide_aliexpress_province('United States', 'alabama', 'BESsMER', auto_correct=True)
        self.assertEqual(correction['city'], 'Bessemer')
        self.assertTrue(valide)

        valide, correction = valide_aliexpress_province('United States', 'Albama', 'besemer', auto_correct=True)
        self.assertEqual(correction['province'], 'Alabama')
        self.assertEqual(correction['city'], 'Bessemer')
        self.assertTrue(valide)

        valide, correction = valide_aliexpress_province('United States', 'arizona', 'wiliams', auto_correct=True)
        self.assertEqual(correction['city'], 'Williams')
        self.assertTrue(valide)

        valide, correction = valide_aliexpress_province('United States', 'Missouri', 'st. louis', auto_correct=True)
        self.assertNotIn('province', correction)
        self.assertEqual(correction['city'], 'Saint louis')
        self.assertTrue(valide)

        # valide, correction = valide_aliexpress_province('United States', 'Missouri', 'St louis', auto_correct=True)
        # self.assertNotIn('province', correction)
        # self.assertEqual(correction['city'], 'Saint louis')
        # self.assertTrue(valide)

        valide, correction = valide_aliexpress_province('United States', 'nevda', 'alamo', auto_correct=True)
        self.assertIn('province', correction)
        self.assertIn('city', correction)
        self.assertEqual(correction['province'], 'Nevada')
        self.assertEqual(correction['city'], 'Alamo')
        self.assertTrue(valide)

    def test_auto_city_fix_es(self):
        valide, correction = valide_aliexpress_province('Spain', 'acoruna', 'abana', auto_correct=True)
        self.assertEqual(correction['province'], 'A Coruna')
        self.assertEqual(correction['city'], 'A Bana')
        self.assertTrue(valide)

    def test_support_other_in_province(self):
        self.assertTrue(support_other_in_province('United Kingdom'))
        self.assertTrue(support_other_in_province('uk'))
        self.assertFalse(support_other_in_province('United States'))
        self.assertFalse(support_other_in_province('US'))

        for country in ['gb', 'Russia', 'nl', 'netherlands', 'cl', 'chile', 'ua', 'ukraine', 'nz', 'new zealand', 'es', 'spain', 'fr', 'france']:
            self.assertTrue(support_other_in_province(country))

    def test_shopify_customer_address(self):
        order = self.get_order()
        order, customer_address = utils.shopify_customer_address(order, aliexpress_fix=True, aliexpress_fix_city=True)

        self.assertEqual(customer_address['province'], 'Alaska')
        self.assertEqual(customer_address['city'], 'Akiak')
        self.assertEqual(customer_address['address2'], '')

    def test_shopify_customer_address_minor_changes_to_match_aliexpress(self):
        order = self.get_order(province='Washington DC', city="malo")
        order, customer_address = utils.shopify_customer_address(order, aliexpress_fix=True, aliexpress_fix_city=True)

        self.assertEqual(customer_address['province'], 'Washington')
        self.assertEqual(customer_address['city'], 'Malo')
        self.assertEqual(customer_address['address2'], '')

    def test_shopify_address_name_title(self):
        order = self.get_order(name="john smith")
        order, customer_address = utils.shopify_customer_address(order, aliexpress_fix=True, aliexpress_fix_city=True)

        self.assertEqual(customer_address['name'], 'John Smith')

    def test_shopify_address_name_and_company(self):
        order = self.get_order(name="john smith", company='TDM LLC')
        order, customer_address = utils.shopify_customer_address(order, aliexpress_fix=True, aliexpress_fix_city=True)

        self.assertEqual(customer_address['name'], 'John Smith - TDM LLC')

    def test_shopify_address_canada(self):
        order = self.get_order(
            country='Canada', country_code='CA', province='Newfoundland', city="Stephenville", zip='ACF855')
        order, customer_address = utils.shopify_customer_address(order, aliexpress_fix=True, aliexpress_fix_city=True)

        self.assertEqual(customer_address['province'], 'Newfoundland and Labrador')
        self.assertEqual(customer_address['city'], 'Stephenville')
        self.assertEqual(customer_address['zip'], 'ACF855')

    def test_shopify_address_canada_unmatch(self):
        order = self.get_order(
            country='Canada', country_code='CA', province='Newfoundland', city="Not Found", zip='acf 855 ')
        order, customer_address = utils.shopify_customer_address(order, aliexpress_fix=True, aliexpress_fix_city=True)

        self.assertEqual(customer_address['province'], 'Newfoundland and Labrador')
        self.assertEqual(customer_address['city'], 'Not Found')
        self.assertEqual(customer_address['zip'], 'ACF855')

    def test_shopify_address_spain(self):
        order = self.get_order(country='SPAIN', country_code='ES', province='Madrid', city="Batres")
        order, customer_address = utils.shopify_customer_address(order, aliexpress_fix=True, aliexpress_fix_city=True)

        self.assertEqual(customer_address['province'], 'Madrid')
        self.assertEqual(customer_address['city'], 'Batres')

        order = self.get_order(country='SPAIN', country_code='ES', province='Madrid', city="Batres", address="55 BIS 1°A")
        order, customer_address = utils.shopify_customer_address(order, aliexpress_fix=True, aliexpress_fix_city=True)

        self.assertEqual(customer_address['address'], '55 BIS 1 A')

        order = self.get_order(country='SPAIN', country_code='ES', province='Madrid', city="Batres", address="55 BIS A° 1")
        order, customer_address = utils.shopify_customer_address(order, aliexpress_fix=True, aliexpress_fix_city=True)

        self.assertEqual(customer_address['address'], '55 BIS A 1')

        order = self.get_order(country='SPAIN', country_code='ES', province='Madrid', city="Batres", address="55 BIS \xc2\xba1")
        order, customer_address = utils.shopify_customer_address(order, aliexpress_fix=True, aliexpress_fix_city=True)

        self.assertEqual(customer_address['address'], '55 BIS 1')

    def test_shopify_address_spain_unmatch(self):
        order = self.get_order(country='Spain', country_code='ES', province='Madrid', city="Not Found")
        order, customer_address = utils.shopify_customer_address(order, aliexpress_fix=True, aliexpress_fix_city=True)

        self.assertEqual(customer_address['province'], 'Other')
        self.assertEqual(customer_address['city'], 'Not Found, Madrid')

    def test_shopify_address_france_match(self):
        order = self.get_order(country='France', country_code='FR', province='Corse', city="Corse-du-Sud")
        order, customer_address = utils.shopify_customer_address(order, aliexpress_fix=True, aliexpress_fix_city=True)

        self.assertEqual(customer_address['province'], 'Corse')
        self.assertEqual(customer_address['city'], 'Corse-du-Sud')

    def test_shopify_address_france_unmatch(self):
        order = self.get_order(country='France', country_code='FR', province='NoProvince', city="NoCity")
        order, customer_address = utils.shopify_customer_address(order, aliexpress_fix=True, aliexpress_fix_city=True)

        self.assertEqual(customer_address['province'], 'Other')
        self.assertEqual(customer_address['city'], 'NoCity, NoProvince')

    def test_shopify_address_uk(self):
        order = self.get_order(country='United Kingdom', country_code='UK', province='England', city="North Yorkshire", zip="WC1B3DG")
        order, customer_address = utils.shopify_customer_address(order, aliexpress_fix=True, aliexpress_fix_city=True)

        self.assertEqual(customer_address['province'], 'England')
        self.assertEqual(customer_address['city'], 'North Yorkshire')
        self.assertEqual(customer_address['zip'], 'WC1B 3DG')

    def test_shopify_address_uk_unmatch(self):
        order = self.get_order(country='UNITED KINGDOM', country_code='GB', province='England', city="Not Found")
        order, customer_address = utils.shopify_customer_address(order, aliexpress_fix=True, aliexpress_fix_city=True)

        self.assertEqual(customer_address['province'], 'Other')
        self.assertEqual(customer_address['city'], 'Not Found, England')

    def test_shopify_address_uk_unmatch2(self):
        order = self.get_order(country='UNITED KINGDOM', country_code='GB', province='Xngnd', city="North XYorkshire")
        order, customer_address = utils.shopify_customer_address(order, aliexpress_fix=True, aliexpress_fix_city=True)

        self.assertEqual(customer_address['province'], 'Other')
        self.assertEqual(customer_address['city'], 'North XYorkshire, Xngnd')

    def test_shopify_address_uk_unmatch3(self):
        order = self.get_order(country='UNITED KINGDOM', country_code='GB', province='Englaand', city="City ofBristol")
        order, customer_address, corrections = utils.shopify_customer_address(
            order, aliexpress_fix=True, aliexpress_fix_city=True, return_corrections=True)

        self.assertIn('city', corrections)
        self.assertIn('province', corrections)

        self.assertEqual(customer_address['province'], 'England')
        self.assertEqual(customer_address['city'], 'City of Bristol')

    def test_shopify_customer_us(self):
        order = self.get_order(province='Alabama', city='alexander city')
        order, customer_address = utils.shopify_customer_address(order, aliexpress_fix=True, aliexpress_fix_city=True)

        self.assertEqual(customer_address['province'], 'Alabama')
        self.assertEqual(customer_address['city'], 'Alexander city')
        self.assertEqual(customer_address['address2'], '')

    def test_shopify_customer_us_unmatch(self):
        order = self.get_order(province='Alabama', city='alxxansity')
        order, customer_address = utils.shopify_customer_address(order, aliexpress_fix=True, aliexpress_fix_city=True)

        self.assertEqual(customer_address['province'], 'Alabama')
        self.assertEqual(customer_address['city'], 'Other')
        self.assertEqual(customer_address['address2'], 'alxxansity,')

    def test_shopify_customer_us_unmatch2(self):
        order = self.get_order(province='Texas', city='xts', address2='2nd Apt. N 555,  ')
        order, customer_address = utils.shopify_customer_address(order, aliexpress_fix=True, aliexpress_fix_city=True)

        self.assertEqual(customer_address['province'], 'Texas')
        self.assertEqual(customer_address['city'], 'Other')
        self.assertEqual(customer_address['address2'], '2nd Apt. N 555, xts,')

    def test_shopify_customer_il_zip_padding(self):
        order = self.get_order(country_code='IL', country='Israel', zip="55966")
        order, customer_address = utils.shopify_customer_address(order, aliexpress_fix=True, aliexpress_fix_city=True)

        self.assertEqual(customer_address['zip'], '0055966')

        order = self.get_order(country_code='IL', country='Israel', zip="11-55-967")
        order, customer_address = utils.shopify_customer_address(order, aliexpress_fix=True, aliexpress_fix_city=True)

        self.assertEqual(customer_address['zip'], '1155967')


class UpdateVariantsDataTestCase(BaseTestCase):
    def setUp(self):
        red_image = 'http://cdn.example/com/image1.png'
        blue_image = 'http://cdn.example/com/image2.png'
        green_image = 'http://cdn.example/com/image3.png'
        self.red_image_hash = hash_url_filename(red_image)
        self.blue_image_hash = hash_url_filename(blue_image)
        self.green_image_hash = hash_url_filename(green_image)

        self.shopify_data = {
            'options': [
                {
                    'name': 'Colour',
                    'values': [
                        'red',
                        'blue',
                        'green',
                    ],
                },
                {
                    'name': 'Size',
                    'values': [
                        'small',
                        'large',
                    ],
                },
            ],
            'images': [
                {
                    'id': 1,
                    'src': red_image
                },
                {
                    'id': 2,
                    'src': blue_image
                },
                {
                    'id': 3,
                    'src': green_image
                },
            ],
            'variants': [
                {
                    'image_id': 1,
                    'option1': 'red',
                    'option2': 'small',
                },
                {
                    'image_id': 1,
                    'option1': 'red',
                    'option2': 'large',
                },
                {
                    'image_id': 2,
                    'option1': 'blue',
                    'option2': 'small',
                },
                {
                    'image_id': 2,
                    'option1': 'blue',
                    'option2': 'large',
                },
                {
                    'image_id': 3,
                    'option1': 'green',
                    'option2': 'small',
                },
                {
                    'image_id': 3,
                    'option1': 'green',
                    'option2': 'large',
                },
            ],
        }

        self.product_data = {
            'images': [
                'http://differentcdn.example.com/image1.png',
                'http://differentcdn.example.com/image2.png',
            ],
            'variants': [
                {
                    'title': 'Color',
                    'values': [
                        'red',
                        'blue',
                    ],
                },
                {
                    'title': 'Size',
                    'values': [
                        'small',
                        'large',
                    ],
                },
            ],
            'variants_images': {
                self.red_image_hash: 'red',
                self.blue_image_hash: 'blue',
            },
        }

        self.product = ShopifyProductFactory()
        self.get_shopify_product = utils.get_shopify_product = Mock(return_value=self.shopify_data)

    def test_must_call_get_shopify_product(self):
        utils.update_variants_data(self.product, self.product_data)
        self.assertTrue(self.get_shopify_product.called)

    def test_must_update_product_data_variants(self):
        utils.update_variants_data(self.product, self.product_data)
        shopify_variants = self.shopify_data['options']
        for num, variant in enumerate(self.product_data['variants']):
            self.assertEqual(variant['title'], shopify_variants[num]['name'])
            self.assertEqual(variant['values'], shopify_variants[num]['values'])

    def test_must_update_variants_images(self):
        utils.update_variants_data(self.product, self.product_data)
        variants_images = self.product_data['variants_images']
        self.assertEqual(variants_images[self.red_image_hash], 'red')
        self.assertEqual(variants_images[self.blue_image_hash], 'blue')
        self.assertEqual(variants_images[self.green_image_hash], 'green')

    def test_must_update_images(self):
        utils.update_variants_data(self.product, self.product_data)
        shopify_data_images = [img['src'] for img in self.shopify_data['images']]
        self.assertEqual(self.product_data['images'], shopify_data_images)


class ShopifyBoardTestCase(BaseTestCase):
    def setUp(self):
        self.user = UserFactory(username='test')
        self.password = 'test'
        self.user.set_password(self.password)
        self.user.save()
        self.store = ShopifyStoreFactory(id=1)
        self.board = ShopifyBoardFactory(user=self.user)
        self.board.config = json.dumps({'type': 'Test Category'})
        self.board.save()

        self.saved_product = ShopifyProductFactory(store=self.store, user=self.user)
        self.saved_product.shopify_id = 0
        self.saved_product.save()

        self.connected_product = ShopifyProductFactory(store=self.store, user=self.user)
        self.connected_product.shopify_id = 1
        self.connected_product.save()

    def test_attach_saved_product_to_multiple_boards(self):
        board2 = ShopifyBoardFactory(user=self.user)

        utils.attach_boards_with_product(self.user, self.saved_product, [self.board.id, board2.id])
        utils.attach_boards_with_product(self.user, self.connected_product, [self.board.id, board2.id])

        self.assertEqual(self.board.saved_count(), 1)
        self.assertEqual(board2.saved_count(), 1)

    def test_attach_connected_product_to_multiple_boards(self):
        board2 = ShopifyBoardFactory(user=self.user)

        utils.attach_boards_with_product(self.user, self.saved_product, [self.board.id, board2.id])
        utils.attach_boards_with_product(self.user, self.connected_product, [self.board.id, board2.id])

        self.assertEqual(self.board.connected_count(), 1)
        self.assertEqual(board2.connected_count(), 1)

    def test_smart_board_by_connected_product(self):
        self.connected_product.data = json.dumps({'type': 'Test Category', 'title': 'Testing'})
        self.connected_product.save()

        utils.smart_board_by_product(self.user, self.saved_product)
        utils.smart_board_by_product(self.user, self.connected_product)
        self.assertEqual(self.board.connected_count(), 1)

    def test_smart_board_by_saved_product(self):
        self.saved_product.data = json.dumps({'type': 'Test Category', 'title': 'Testing'})
        self.saved_product.save()

        utils.smart_board_by_product(self.user, self.connected_product)
        utils.smart_board_by_product(self.user, self.saved_product)
        self.assertEqual(self.board.saved_count(), 1)


class TestUploadFileToS3(BaseTestCase):
    def test_with_fp(self):
        url = 'http://example.com/test.jpg'
        user_id = 1
        fp = 'test fp'

        with patch('leadgalaxy.utils.aws_s3_upload') as mock_aws_upload, \
                patch('leadgalaxy.utils.random_filename', return_value='rand'):
            utils.upload_file_to_s3(url, user_id, fp=fp)

            mock_aws_upload.assert_called_with(
                filename='uploads/u1/rand',
                fp=fp,
                mimetype='image/jpeg',
                bucket_name=settings.S3_UPLOADS_BUCKET
            )

    def test_without_fp(self):
        url = 'http://example.com/test.jpg'
        user_id = 1
        data = b'test fp'

        mock_get = MagicMock()
        mock_get.content = data
        with patch('leadgalaxy.utils.aws_s3_upload') as mock_aws_upload, \
                patch('requests.get', return_value=mock_get), \
                patch('io.BytesIO', return_value='bytes'), \
                patch('leadgalaxy.utils.random_filename', return_value='rand'):
            utils.upload_file_to_s3(url, user_id)

            mock_aws_upload.assert_called_with(
                filename='uploads/u1/rand',
                fp='bytes',
                mimetype='image/jpeg',
                bucket_name=settings.S3_UPLOADS_BUCKET
            )
