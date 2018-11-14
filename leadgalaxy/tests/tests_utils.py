# -*- coding: utf-8 -*-

import re
import random
from django.conf import settings
from redis.exceptions import LockError

from lib.test import BaseTestCase
from shopify_orders.models import ShopifyOrder, ShopifyOrderLine
from leadgalaxy import utils
from leadgalaxy.models import (
    ShopifyOrderTrack
)

from shopified_core.shipping_helper import (
    get_uk_province,
    valide_aliexpress_province,
    support_other_in_province,
)

from leadgalaxy.tests.factories import UserFactory

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
        self.assertEqual(data['fulfillment']['tracking_url'], "http://track.aftership.com/{}".format(track.source_tracking))
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
        self.assertEqual(data['fulfillment']['tracking_url'], "http://track.aftership.com/{}".format(track.source_tracking))

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
        self.assertEqual(data['fulfillment']['tracking_url'], "http://uncommonnow.aftership.com/{}".format(track.source_tracking))

    def test_custom_aftership_domain_with_us_epacket(self):
        # User have a custom tracking, it should be used even for ePacket-US instead of USPS
        track = self.create_track('5415135175', '1654811', 'MA7565915257226HK', 'US')
        data = utils.order_track_fulfillment(order_track=track, user_config={'aftership_domain': {"1": 'uncommonnow'}})
        self.assertEqual(data['fulfillment']['tracking_company'], "Other")
        self.assertEqual(data['fulfillment']['tracking_url'], "http://uncommonnow.aftership.com/{}".format(track.source_tracking))

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
        self.assertEqual(data['fulfillment']['tracking_urls'], ['http://uncommonnow.aftership.com/MA7565915257226HK', 'http://uncommonnow.aftership.com/MA7565915257227HK'])

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
        self.assertEqual(data['fulfillment']['tracking_url'], "http://track.aftership.com/{}".format(self.fulfillment_data['source_tracking']))

    def test_manual_fulfilement_aftership_custom(self):
        # Custom Aftership domain
        self.fulfillment_data['source_tracking'] = 'MA7565915257226HK'
        self.fulfillment_data['use_usps'] = False
        self.fulfillment_data['store_id'] = 2
        self.fulfillment_data['user_config']['aftership_domain'] = {"2": "uncommonnow"}
        data = utils.order_track_fulfillment(**self.fulfillment_data)
        self.assertEqual(data['fulfillment']['tracking_url'], "http://uncommonnow.aftership.com/{}".format(self.fulfillment_data['source_tracking']))

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
        self.assertEqual(data['fulfillment']['tracking_url'], "http://uncommonnow.aftership.com/{}".format(self.fulfillment_data['source_tracking']))

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
        self.fulfillment_data['user_config']['aftership_domain'] = {"2": "http://track.uncommonnow.com/{{tracking_number}}"}
        data = utils.order_track_fulfillment(**self.fulfillment_data)
        self.assertEqual(data['fulfillment']['tracking_url'], "http://track.uncommonnow.com/{}".format(self.fulfillment_data['source_tracking']))

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
        self.assertEqual(data['fulfillment']['tracking_url'], "http://track.uncommonnow.com/{}".format(self.fulfillment_data['source_tracking']))

    def test_manual_fulfilement_aftership_custom_url_fix_scheme(self):
        # Custom Aftership domain
        self.fulfillment_data['source_tracking'] = 'MA7565915257226HK'
        self.fulfillment_data['use_usps'] = False
        self.fulfillment_data['store_id'] = 2
        self.fulfillment_data['user_config']['aftership_domain'] = {"2": "//track.uncommonnow.com/{{tracking_number}}"}
        data = utils.order_track_fulfillment(**self.fulfillment_data)
        self.assertEqual(data['fulfillment']['tracking_url'], "http://track.uncommonnow.com/{}".format(self.fulfillment_data['source_tracking']))

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


class OrdersTestCase(BaseTestCase):
    def setUp(self):
        pass

    def test_order_notes(self):
        order_id = 4905209738
        line_id = 9309669834

        store = ShopifyStoreFactory()
        order = utils.get_shopify_order(store, order_id)
        self.assertEqual(order['id'], order_id)

        note1 = 'Test Note #%s' % utils.random_hash()
        utils.set_shopify_order_note(store, order_id, note1)

        self.assertEqual(note1, utils.get_shopify_order_note(store, order_id))

        note2 = 'An other Test Note #%s' % utils.random_hash()
        utils.add_shopify_order_note(store, order_id, note2)

        order_note = utils.get_shopify_order_note(store, order_id)
        self.assertIn(note1, order_note)
        self.assertIn(note2, order_note)

        line = utils.get_shopify_order_line(store, order_id, line_id)
        self.assertEqual(line['id'], line_id)

        line, current_note = utils.get_shopify_order_line(store, order_id, line_id, note=True)
        self.assertEqual(line['id'], line_id)
        self.assertIsNotNone(current_note)

        note3 = 'Yet An other Test Note #%s' % utils.random_hash()
        utils.add_shopify_order_note(store, order_id, note3, current_note=current_note)

        order_note = utils.get_shopify_order_note(store, order_id)

        self.assertIn(note1, order_note)
        self.assertIn(note2, order_note)
        self.assertIn(note3, order_note)

        utils.set_shopify_order_note(store, order_id, '')

    def test_order_updater_note(self):
        store = ShopifyStoreFactory()
        order_id = 579111223384

        note = 'Test Note #%s' % utils.random_hash()

        updater = utils.ShopifyOrderUpdater(store, order_id)
        updater.add_note(note)

        updater.reset('notes')

        try:
            updater.save_changes()
            self.assertEqual(note, utils.get_shopify_order_note(store, order_id))
        except LockError:
            pass

    def test_order_updater_note_unicode(self):
        store = ShopifyStoreFactory()
        order_id = 579111518296

        feed = requests.get('http://feeds.bbci.co.uk/japanese/rss.xml')
        if not feed.ok:
            return

        unicode_text = random.choice([i[1] for i in re.findall(r'title>(<!\[CDATA\[)([^>]+)(]]>)</title', feed.text)])

        utils.set_shopify_order_note(store, order_id, unicode_text)

        note = 'Test Note #%s' % utils.random_hash()

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

    def test_order_updater_tags(self):
        store = ShopifyStoreFactory()
        order_id = 579111714904

        tag = '#%s' % utils.random_hash()

        updater = utils.ShopifyOrderUpdater(store, order_id)
        updater.add_tag(tag)

        updater.reset('tags')

        try:
            updater.save_changes()
        except LockError:
            return

        self.assertEqual(tag, utils.get_shopify_order(store, order_id)['tags'])

    def test_order_updater_attributes(self):
        store = ShopifyStoreFactory()
        order_id = 579111845976

        attrib = {'name': utils.random_hash(), 'value': utils.random_hash()}

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

        updater.add_attribute({'name': utils.random_hash(), 'value': utils.random_hash()})
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
        updater.add_attribute({'name': utils.random_hash(), 'value': utils.random_hash()})

        self.assertTrue(updater.have_changes())


class UtilsTestCase(BaseTestCase):
    def setUp(self):
        pass

    def test_get_domain(self):
        self.assertEqual(utils.get_domain('www.aliexpress.com'), 'aliexpress')
        self.assertEqual(utils.get_domain('http://www.aliexpress.com'), 'aliexpress')
        self.assertEqual(utils.get_domain('www.aliexpress.com/item/UNO-R3/32213964945.html'), 'aliexpress')
        self.assertEqual(utils.get_domain('http://www.aliexpress.com/item/UNO-R3/32213964945.html'), 'aliexpress')
        self.assertEqual(utils.get_domain('http://s.aliexpress.com/seeplink.html?id=32213964945'), 'aliexpress')
        self.assertEqual(utils.get_domain('www.ebay.com/itm/131696353919'), 'ebay')
        self.assertEqual(utils.get_domain('http://www.ebay.com/itm/131696353919'), 'ebay')
        self.assertEqual(utils.get_domain('www.amazon.co.uk'), 'amazon')
        self.assertEqual(utils.get_domain('www.amazon.fr'), 'amazon')
        self.assertEqual(utils.get_domain('www.amazon.de'), 'amazon')
        self.assertEqual(utils.get_domain('www.wanelo.co'), 'wanelo')
        self.assertEqual(utils.get_domain('http://www.costco.com/Jura.product.100223622.html'), 'costco')
        self.assertEqual(utils.get_domain('http://www.qvc.com/egiftcards'), 'qvc')
        self.assertEqual(utils.get_domain('http://shopified-app-ci.myshopify.com/admin/products/1234'), 'myshopify')

        self.assertEqual(utils.get_domain('www.aliexpress.com', full=True), 'www.aliexpress.com')
        self.assertEqual(utils.get_domain('http://www.aliexpress.com/item/UNO-R3/32213964945.html', full=True), 'www.aliexpress.com')
        self.assertEqual(utils.get_domain('http://aliexpress.com/item/UNO-R3/32213964945.html', full=True), 'aliexpress.com')
        self.assertEqual(utils.get_domain('http://www.ebay.com/itm/131696353919', full=True), 'www.ebay.com')
        self.assertEqual(utils.get_domain('http://shopified-app-ci.myshopify.com/admin/products/1234', full=True), 'shopified-app-ci.myshopify.com')

    def test_remove_link_query(self):
        self.assertEqual(
            utils.remove_link_query('https://cdn.shopify.com/s/files/1/1013/1174/products/Fashion-Metal---magnification-wholesale.jpeg?v=1452639314'),
            'https://cdn.shopify.com/s/files/1/1013/1174/products/Fashion-Metal---magnification-wholesale.jpeg')

        self.assertEqual(
            utils.remove_link_query('http://www.ebay.com/itm/131696353919?v=1452639314'),
            'http://www.ebay.com/itm/131696353919')

        self.assertEqual(
            utils.remove_link_query('http://www.ebay.com/itm/131696353919#hash:12'),
            'http://www.ebay.com/itm/131696353919')

        self.assertEqual(
            utils.remove_link_query('https://i.ebayimg.com/images/g/RHIAAOSwQaJXRBkE/s-l500.jpg?hash=1e56ace2'),
            'https://i.ebayimg.com/images/g/RHIAAOSwQaJXRBkE/s-l500.jpg')

        self.assertEqual(
            utils.remove_link_query('http://www.ebay.com/itm/131696353919?v=1452639314#hash:12'),
            'http://www.ebay.com/itm/131696353919')

        self.assertEqual(
            utils.remove_link_query('http://g03.a.alicdn.com/kf/HTB13OOBLFXXXXcoXpXXq6xXFXXXp/Vente-chaude-vinyle-amovible-stickers-muraux-t&ecirc;te-de-cheval-peintures-murales-salon-d&eacute;corative-animaux-accueil-autocollant.jpg'),
            'http://g03.a.alicdn.com/kf/HTB13OOBLFXXXXcoXpXXq6xXFXXXp/Vente-chaude-vinyle-amovible-stickers-muraux-t&ecirc;te-de-cheval-peintures-murales-salon-d&eacute;corative-animaux-accueil-autocollant.jpg')

        self.assertEqual(
            utils.remove_link_query('www.aliexpress.com/store/1185416?spm=2114.10010108.0.627.LN13ZN'),
            'http://www.aliexpress.com/store/1185416')

        self.assertEqual(
            utils.remove_link_query('http://www.ebay.com/itm/131696353919?'),
            'http://www.ebay.com/itm/131696353919')

        self.assertEqual(
            utils.remove_link_query('http://www.ebay.com/itm/131696353919'),
            'http://www.ebay.com/itm/131696353919')

        self.assertEqual(
            utils.remove_link_query('//www.ebay.com/itm/131696353919'),
            'http://www.ebay.com/itm/131696353919')

        self.assertEqual(
            utils.remove_link_query('://www.ebay.com/itm/131696353919'),
            'http://www.ebay.com/itm/131696353919')

    def test_upload_from_url(self):
        aviary_url = ('://s3.amazonaws.com/feather-files-aviary-prod-us-east-1',
                      '/220489e3e16f4691bc88d1ef81e05a8b/2016-05-24/00b4838ae29840d1bcfa6d2fa570ab02.png')

        self.assertTrue(utils.upload_from_url('http' + ''.join(aviary_url)))
        self.assertTrue(utils.upload_from_url('https' + ''.join(aviary_url)))

        self.assertTrue(utils.upload_from_url('http://i.ebayimg.com/images/g/RHIAAOSwQaJXRBkE/s-l500.jpg'))
        self.assertTrue(utils.upload_from_url('http://shopifiedapp.s3.amazonaws.com/uploads/u1/d3d1aed3576999dca762cad33b31c79a.png'))
        self.assertTrue(utils.upload_from_url('http://%s.s3.amazonaws.com/uploads/u1/d3d1aed3576999dca762cad33b31c79a.png' % settings.S3_UPLOADS_BUCKET))
        self.assertTrue(utils.upload_from_url('http://%s.s3.amazonaws.com/uploads/u1/d3d1aed3576999dca762cad33b31c79a.png' % settings.S3_STATIC_BUCKET))
        self.assertTrue(utils.upload_from_url('http://d2kadg5e284yn4.cloudfront.net/uploads/u1/d3d1aed3576999dca762cad33b31c79a.png'))
        self.assertTrue(utils.upload_from_url('https://betaimages.sunfrogshirts.com/m_1349black.jpg'))
        self.assertTrue(utils.upload_from_url('https://cdn.shopify.com/s/files/1/1013/1174/products/Fashion-Metal---magnification-wholesale.jpeg'))
        self.assertTrue(utils.upload_from_url('https://cdn.shopify.com/s/files/1/1013/1174/products/Fashion-Metal---magnification-wholesale.jpeg?v=1452639314'))
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
        self.assertEqual(utils.ensure_title('james'), 'James')
        self.assertEqual(utils.ensure_title('James'), 'James')
        self.assertEqual(utils.ensure_title('JAMES'), 'JAMES')

    def test_ensure_title_str(self):
        self.assertEqual(utils.ensure_title('james bond'), 'James Bond')

    def test_ensure_title_unicode(self):
        self.assertEqual(utils.ensure_title(u'vari\xe9t\xe9'), u'vari\xe9t\xe9')


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
                "address1": u"5th Ave üop",
            }
        }

        order, addr = utils.shopify_customer_address(order)
        self.assertEqual(addr['address1'], '5th Ave uop')

        order, addr = utils.shopify_customer_address(order, german_umlauts=True)
        self.assertEqual(addr['address1'], '5th Ave ueop')

        vals = {
            u"5TH AVE ÜOP": '5TH AVE UEOP',
            u"5th Ave äop": '5th Ave aeop',
            u"5TH AVE ÄOP": '5TH AVE AEOP',
            u"5th Ave öop": '5th Ave oeop',
            u"5TH AVE ÖOP": '5TH AVE OEOP',
        }

        for k, v in vals.items():
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

    def test_uk_validate_address(self):
        self.assertTrue(valide_aliexpress_province('uk', 'england', 'Kent'))
        self.assertFalse(valide_aliexpress_province('uk', 'england', 'NotFound'))
        self.assertFalse(valide_aliexpress_province('uk', 'NotFound', 'Kent'))
        self.assertFalse(valide_aliexpress_province('au', 'New South Wales', 'Teven'))

    def test_uk_fix_address(self):
        self.assertEqual(get_uk_province('Kent'), 'england')
        self.assertEqual(get_uk_province('Avon'), 'Other')

    def test_support_other_in_province(self):
        self.assertTrue(support_other_in_province('United Kingdom'))
        self.assertTrue(support_other_in_province('uk'))
        self.assertFalse(support_other_in_province('United States'))
        self.assertFalse(support_other_in_province('US'))

        self.assertFalse(support_other_in_province('Spain'))

        for country in ['gb', 'Russia', 'au', 'australia', 'nl', 'netherlands', 'cl', 'chile', 'ua', 'ukraine', 'nz', 'new zealand']:
            self.assertTrue(support_other_in_province(country))

    def test_shopify_customer_address(self):
        order = self.get_order()
        order, customer_address = utils.shopify_customer_address(order, aliexpress_fix=True, fix_aliexpress_city=True)

        self.assertEqual(customer_address['province'], 'Alaska')
        self.assertEqual(customer_address['city'], 'Akiak')
        self.assertEqual(customer_address['address2'], '')

    def test_shopify_customer_address_minor_changes_to_match_aliexpress(self):
        order = self.get_order(province='Washington DC', city="malo")
        order, customer_address = utils.shopify_customer_address(order, aliexpress_fix=True, fix_aliexpress_city=True)

        self.assertEqual(customer_address['province'], 'Washington')
        self.assertEqual(customer_address['city'], 'malo')
        self.assertEqual(customer_address['address2'], '')

    def test_shopify_address_name_title(self):
        order = self.get_order(name="john smith")
        order, customer_address = utils.shopify_customer_address(order, aliexpress_fix=True, fix_aliexpress_city=True)

        self.assertEqual(customer_address['name'], 'John Smith')

    def test_shopify_address_name_and_company(self):
        order = self.get_order(name="john smith", company='TDM LLC')
        order, customer_address = utils.shopify_customer_address(order, aliexpress_fix=True, fix_aliexpress_city=True)

        self.assertEqual(customer_address['name'], 'John Smith - TDM LLC')

    def test_shopify_address_canada(self):
        order = self.get_order(
            country='Canada', country_code='CA', province='Newfoundland', city="Stephenville", zip='ACF855')
        order, customer_address = utils.shopify_customer_address(order, aliexpress_fix=True, fix_aliexpress_city=True)

        self.assertEqual(customer_address['province'], 'Newfoundland and Labrador')
        self.assertEqual(customer_address['city'], 'Stephenville')
        self.assertEqual(customer_address['zip'], 'ACF855')

    def test_shopify_address_canada_unmatch(self):
        order = self.get_order(
            country='Canada', country_code='CA', province='Newfoundland', city="Not Found", zip='acf 855 ')
        order, customer_address = utils.shopify_customer_address(order, aliexpress_fix=True, fix_aliexpress_city=True)

        self.assertEqual(customer_address['province'], 'Newfoundland and Labrador')
        self.assertEqual(customer_address['city'], 'Not Found')
        self.assertEqual(customer_address['zip'], 'ACF855')

    def test_shopify_address_spain(self):
        order = self.get_order(country='SPAIN', country_code='ES', province='Madrid', city="Batres")
        order, customer_address = utils.shopify_customer_address(order, aliexpress_fix=True, fix_aliexpress_city=True)

        self.assertEqual(customer_address['province'], 'Madrid')
        self.assertEqual(customer_address['city'], 'Batres')

    def test_shopify_address_spain_unmatch(self):
        order = self.get_order(country='Spain', country_code='ES', province='Madrid', city="Not Found")
        order, customer_address = utils.shopify_customer_address(order, aliexpress_fix=True, fix_aliexpress_city=True)

        self.assertEqual(customer_address['province'], 'Madrid')
        self.assertEqual(customer_address['city'], 'Other')
        self.assertEqual(customer_address['address2'], 'Not Found,')

    def test_shopify_address_uk(self):
        order = self.get_order(country='United Kingdom', country_code='UK', province='England', city="North Yorkshire", zip="WC1B3DG")
        order, customer_address = utils.shopify_customer_address(order, aliexpress_fix=True, fix_aliexpress_city=True)

        self.assertEqual(customer_address['province'], 'England')
        self.assertEqual(customer_address['city'], 'North Yorkshire')
        self.assertEqual(customer_address['zip'], 'WC1B 3DG')

    def test_shopify_address_uk_unmatch(self):
        order = self.get_order(country='UNITED KINGDOM', country_code='GB', province='England', city="Not Found")
        order, customer_address = utils.shopify_customer_address(order, aliexpress_fix=True, fix_aliexpress_city=True)

        self.assertEqual(customer_address['province'], 'Other')
        self.assertEqual(customer_address['city'], 'Not Found, England')

        order = self.get_order(country='UNITED KINGDOM', country_code='GB', province='Xngland', city="North Yorkshire")
        order, customer_address = utils.shopify_customer_address(order, aliexpress_fix=True, fix_aliexpress_city=True)

        self.assertEqual(customer_address['province'], 'Other')
        self.assertEqual(customer_address['city'], 'North Yorkshire, Xngland')

    def test_shopify_customer_us(self):
        order = self.get_order(province='Alabama', city='alexander city')
        order, customer_address = utils.shopify_customer_address(order, aliexpress_fix=True, fix_aliexpress_city=True)

        self.assertEqual(customer_address['province'], 'Alabama')
        self.assertEqual(customer_address['city'], 'alexander city')
        self.assertEqual(customer_address['address2'], '')

    def test_shopify_customer_us_unmatch(self):
        order = self.get_order(province='Alabama', city='alexand city')
        order, customer_address = utils.shopify_customer_address(order, aliexpress_fix=True, fix_aliexpress_city=True)

        self.assertEqual(customer_address['province'], 'Alabama')
        self.assertEqual(customer_address['city'], 'Other')
        self.assertEqual(customer_address['address2'], 'alexand city,')

        order = self.get_order(province='Texas', city='Yants', address2='2nd Apt. N 555,  ')
        order, customer_address = utils.shopify_customer_address(order, aliexpress_fix=True, fix_aliexpress_city=True)

        self.assertEqual(customer_address['province'], 'Texas')
        self.assertEqual(customer_address['city'], 'Other')
        self.assertEqual(customer_address['address2'], '2nd Apt. N 555, Yants,')

    def test_shopify_customer_il_zip_padding(self):
        order = self.get_order(country_code='IL', country='Israel', zip="55966")
        order, customer_address = utils.shopify_customer_address(order, aliexpress_fix=True, fix_aliexpress_city=True)

        self.assertEqual(customer_address['zip'], '0055966')

        order = self.get_order(country_code='IL', country='Israel', zip="11-55-967")
        order, customer_address = utils.shopify_customer_address(order, aliexpress_fix=True, fix_aliexpress_city=True)

        self.assertEqual(customer_address['zip'], '1155967')
