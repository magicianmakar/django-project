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


class ShopifyStoreFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = utils.ShopifyStore
        django_get_or_create = ['api_url']

    title = 'uncommonnow'
    api_url = 'https://d43e2fd73231e565c290a548c05f9c1f:c2fb34b864894a4f03e6a00205301de7@rank-engine.myshopify.com'
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


class FulfillmentTestCase(TestCase):
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

    def test_auto_fulfillment(self):
        # Line not found
        track1 = ShopifyOrderTrackFactory(order_id='5415135170', line_id='1654810', source_tracking='MA7565915257226HK', store_id=2)
        data = utils.order_track_fulfillment(order_track=track1, user_config={})
        self.assertEqual(data['fulfillment']['tracking_company'], "Other")
        self.assertEqual(data['fulfillment']['tracking_url'], "https://track.aftership.com/{}".format(track1.source_tracking))
        self.assertEqual(len(data['fulfillment']['line_items']), 1)
        self.assertEqual(data['fulfillment']['line_items'][0]['id'], '1654810')

        # ePacket Order
        track2 = self.create_track('5415135175', '1654811', 'MA7565915257226HK', 'US')
        data = utils.order_track_fulfillment(order_track=track2, user_config={})
        self.assertEqual(data['fulfillment']['tracking_company'], "USPS")
        self.assertIsNone(data['fulfillment'].get('tracking_url'))

        # Unrecognized Carrier
        track3 = self.create_track('5415135176', '1654812', 'YT1614016214415424', 'US')
        data = utils.order_track_fulfillment(order_track=track3, user_config={})
        self.assertEqual(data['fulfillment']['tracking_company'], "Other")
        self.assertEqual(data['fulfillment']['tracking_url'], "https://track.aftership.com/{}".format(track3.source_tracking))

        # Non US address
        track4 = self.create_track('5415135177', '1654813', 'MA7565915257226HK', 'MA')
        data = utils.order_track_fulfillment(order_track=track4, user_config={})
        self.assertEqual(data['fulfillment']['tracking_company'], "Other")

        # Default Confirmation email
        data = utils.order_track_fulfillment(order_track=track1, user_config={})
        self.assertTrue('notify_customer' not in data['fulfillment'])

        data = utils.order_track_fulfillment(order_track=track1, user_config={'send_shipping_confirmation': 'default'})
        self.assertTrue('notify_customer' not in data['fulfillment'])

        # Don't send Confirmation email
        data = utils.order_track_fulfillment(order_track=track1, user_config={'send_shipping_confirmation': 'no'})
        self.assertFalse(data['fulfillment']['notify_customer'])

        # Always send Confirmation email
        data = utils.order_track_fulfillment(order_track=track1, user_config={'send_shipping_confirmation': 'yes'})
        self.assertTrue(data['fulfillment']['notify_customer'])

        # Always send Confirmation email if Tracking is valid
        data = utils.order_track_fulfillment(order_track=track1, user_config={'send_shipping_confirmation': 'yes', 'validate_tracking_number': True})
        self.assertTrue(data['fulfillment']['notify_customer'])

        track5 = self.create_track('5415135176', '1654814', '7565915257226', 'MA')
        data = utils.order_track_fulfillment(order_track=track5, user_config={'send_shipping_confirmation': 'yes', 'validate_tracking_number': True})
        self.assertFalse(data['fulfillment']['notify_customer'])

        # Custom Aftership domain
        data = utils.order_track_fulfillment(order_track=track1, user_config={'aftership_domain': {"2": 'uncommonnow'}})
        self.assertEqual(data['fulfillment']['tracking_url'], "https://uncommonnow.aftership.com/{}".format(track1.source_tracking))

    def test_manual_fulfilement(self):
        fulfillment_data = {
            'line_id': '123456',
            'order_id': '456789123',
            'source_tracking': 'MA7565915257226HK',
            'use_usps': True,
            'user_config': {
                'send_shipping_confirmation': 'yes',
                'validate_tracking_number': False,
                'aftership_domain': 'track'
            }
        }

        data = utils.order_track_fulfillment(**fulfillment_data)
        self.assertEqual(data['fulfillment']['tracking_company'], "USPS")
        self.assertIsNone(data['fulfillment'].get('tracking_url'))
        self.assertTrue(data['fulfillment']['notify_customer'])

        # Empty Tracking
        fulfillment_data['source_tracking'] = ''
        data = utils.order_track_fulfillment(**fulfillment_data)
        self.assertIsNone(data['fulfillment']['tracking_number'])
        self.assertTrue('tracking_url' not in data['fulfillment'])
        self.assertTrue('tracking_company' not in data['fulfillment'])

        # Aftership tracking
        fulfillment_data['source_tracking'] = 'MA7565915257226HK'
        fulfillment_data['use_usps'] = False
        data = utils.order_track_fulfillment(**fulfillment_data)
        self.assertEqual(data['fulfillment']['tracking_company'], "Other")
        self.assertEqual(data['fulfillment']['tracking_url'], "https://track.aftership.com/{}".format(fulfillment_data['source_tracking']))

        # Custom Aftership domain
        fulfillment_data['user_config']['aftership_domain'] = {"2": "uncommonnow"}
        fulfillment_data['store_id'] = 2
        data = utils.order_track_fulfillment(**fulfillment_data)
        self.assertEqual(data['fulfillment']['tracking_url'], "https://uncommonnow.aftership.com/{}".format(fulfillment_data['source_tracking']))

        # Empty Tracking with ShopifyOrder
        self.create_track('456789321', '789456', '', 'US')

        fulfillment_data['source_tracking'] = ''
        fulfillment_data['order_id'] = '456789321'
        fulfillment_data['line_id'] = '789456'
        data = utils.order_track_fulfillment(**fulfillment_data)
        self.assertIsNone(data['fulfillment']['tracking_number'])

        # Assert to not use USPS for Tracking with ShopifyOrder
        self.create_track('456789321', '789456', 'MA7565915257226HK', 'US')

        fulfillment_data['source_tracking'] = 'MA7565915257226HK'
        fulfillment_data['order_id'] = '456789321'
        fulfillment_data['line_id'] = '789456'
        fulfillment_data['use_usps'] = False
        data = utils.order_track_fulfillment(**fulfillment_data)
        self.assertEqual(data['fulfillment']['tracking_company'], "Other")

        # Force USPS use
        fulfillment_data['use_usps'] = True
        data = utils.order_track_fulfillment(**fulfillment_data)
        self.assertEqual(data['fulfillment']['tracking_company'], "USPS")

        # Force USPS use for non valide tracking
        self.create_track('4567893477', '78945611', '7565915257226', 'MA')
        fulfillment_data['order_id'] = '4567893477'
        fulfillment_data['line_id'] = '78945611'
        fulfillment_data['use_usps'] = True
        data = utils.order_track_fulfillment(**fulfillment_data)
        self.assertEqual(data['fulfillment']['tracking_company'], "USPS")


class OrdersTestCase(TestCase):
    def setUp(self):
        pass

    def test_order_notes(self):
        order_id = 2135735813
        line_id = 3896443589

        store = ShopifyStoreFactory()
        order = utils.get_shopify_order(store, order_id)
        self.assertEqual(order['id'], order_id)

        note1 = 'Test Note #%s' % utils.random_hash()
        utils.set_shopify_order_note(store, order_id, note1)

        self.assertEqual(note1, utils.get_shopify_order_note(store, order_id))

        note2 = 'An other Test Note #%s' % utils.random_hash()
        utils.add_shopify_order_note(store, order_id, note2)

        order_note = utils.get_shopify_order_note(store, order_id)
        self.assertTrue(note1 in order_note)
        self.assertTrue(note2 in order_note)

        line = utils.get_shopify_order_line(store, order_id, line_id)
        self.assertEqual(line['id'], line_id)

        line, current_note = utils.get_shopify_order_line(store, order_id, line_id, note=True)
        self.assertEqual(line['id'], line_id)
        self.assertIsNotNone(current_note)

        note3 = 'Yet An other Test Note #%s' % utils.random_hash()
        utils.add_shopify_order_note(store, order_id, note3, current_note=current_note)

        order_note = utils.get_shopify_order_note(store, order_id)

        self.assertTrue(note1 in order_note)
        self.assertTrue(note2 in order_note)
        self.assertTrue(note3 in order_note)


class UtilsTestCase(TestCase):
    def setUp(self):
        pass

    def test_get_domain(self):
        self.assertEqual(utils.get_domain('www.aliexpress.com'), 'aliexpress')
        self.assertEqual(utils.get_domain('http://www.aliexpress.com'), 'aliexpress')
        self.assertEqual(utils.get_domain('www.aliexpress.com/item/UNO-R3/32213964945.html'), 'aliexpress')
        self.assertEqual(utils.get_domain('http://www.aliexpress.com/item/UNO-R3/32213964945.html'), 'aliexpress')
        self.assertEqual(utils.get_domain('www.ebay.com/itm/131696353919'), 'ebay')
        self.assertEqual(utils.get_domain('http://www.ebay.com/itm/131696353919'), 'ebay')

        self.assertEqual(utils.get_domain('www.aliexpress.com', full=True), 'www.aliexpress.com')
        self.assertEqual(utils.get_domain('http://www.aliexpress.com/item/UNO-R3/32213964945.html', full=True), 'www.aliexpress.com')
        self.assertEqual(utils.get_domain('http://aliexpress.com/item/UNO-R3/32213964945.html', full=True), 'aliexpress.com')
        self.assertEqual(utils.get_domain('http://www.ebay.com/itm/131696353919', full=True), 'www.ebay.com')

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

    def test_upload_from_url(self):
        aviary_url = ('://s3.amazonaws.com/feather-files-aviary-prod-us-east-1',
                      '/220489e3e16f4691bc88d1ef81e05a8b/2016-05-24/00b4838ae29840d1bcfa6d2fa570ab02.png')

        self.assertTrue(utils.upload_from_url('http' + ''.join(aviary_url)))
        self.assertTrue(utils.upload_from_url('https' + ''.join(aviary_url)))

        self.assertTrue(utils.upload_from_url('http://i.ebayimg.com/images/g/RHIAAOSwQaJXRBkE/s-l500.jpg'))
        self.assertTrue(utils.upload_from_url('http://shopifiedapp.s3.amazonaws.com/uploads/u1/d3d1aed3576999dca762cad33b31c79a.png'))
        self.assertTrue(utils.upload_from_url('https://betaimages.sunfrogshirts.com/m_1349black.jpg'))
        self.assertTrue(utils.upload_from_url('https://cdn.shopify.com/s/files/1/1013/1174/products/Fashion-Metal---magnification-wholesale.jpeg'))
        self.assertTrue(utils.upload_from_url('https://cdn.shopify.com/s/files/1/1013/1174/products/Fashion-Metal---magnification-wholesale.jpeg?v=1452639314'))

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
