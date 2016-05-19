from django.test import TestCase
from leadgalaxy import utils

import factory


class ShopifyOrderTrackFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = utils.ShopifyOrderTrack
        django_get_or_create = ['line_id', 'order_id', 'user_id']

    line_id = '1654811'
    order_id = '5415135175'
    source_tracking = 'MA7565915257226HK'
    user_id = 1


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


class UtilsTestCase(TestCase):
    def setUp(self):
        pass

    def create_track(self, order_id, line_id, source_tracking, country_code):
        track = ShopifyOrderTrackFactory(order_id=order_id, line_id=line_id, source_tracking=source_tracking)
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


    def test_tracking_fulfillment(self):
        # Line not found
        track = ShopifyOrderTrackFactory(order_id='5415135170', line_id='1654810', source_tracking='MA7565915257226HK')
        data = utils.order_track_fulfillment(track)
        self.assertEqual(data['fulfillment']['tracking_company'], "Other")
        self.assertEqual(data['fulfillment']['tracking_url'], "https://track.aftership.com/{}".format(track.source_tracking))
        self.assertEqual(len(data['fulfillment']['line_items']), 1)
        self.assertEqual(data['fulfillment']['line_items'][0]['id'], '1654810')

        # ePacket Order
        track = self.create_track('5415135175', '1654811', 'MA7565915257226HK', 'US')
        data = utils.order_track_fulfillment(track)
        self.assertEqual(data['fulfillment']['tracking_company'], "USPS")
        self.assertIsNone(data['fulfillment'].get('tracking_url'))

        # Unrecognized Carrier
        track = self.create_track('5415135176', '1654812', 'YT1614016214415424', 'US')
        data = utils.order_track_fulfillment(track)
        self.assertEqual(data['fulfillment']['tracking_company'], "Other")
        self.assertEqual(data['fulfillment']['tracking_url'], "https://track.aftership.com/{}".format(track.source_tracking))

        # Non US address
        track = self.create_track('5415135177', '1654813', 'MA7565915257226HK', 'MA')
        data = utils.order_track_fulfillment(track)
        self.assertEqual(data['fulfillment']['tracking_company'], "Other")
