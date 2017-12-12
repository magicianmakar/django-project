import json

from mock import patch, Mock
from requests.exceptions import HTTPError

from django.test import TestCase
from django.core.cache import cache, caches

from leadgalaxy.models import User
from commercehq_core import utils
from commercehq_core.models import CommerceHQStore
from leadgalaxy.utils import (
    random_hash
)
from .factories import (
    CommerceHQStoreFactory,
    CommerceHQOrderTrackFactory,
    CommerceHQProductFactory,
)
from ..utils import (
    get_shipping_carrier,
    check_notify_customer,
    add_aftership_to_store_carriers,
    cache_fulfillment_data,
    update_product_data_images,
    hash_url_filename,
)


CHQ_API_URL = 'chq-shopified-dev.commercehqdev.com'
CHQ_API_KEY = 'i7_-EFt8qb8MPb4ey0nTQ2BRT88DjSaH'
CHQ_API_PASSWORD = 'UVJJqis5sWxSLxoEXOuAM672n2d66xfs'


class GetShippingCarrierTestCase(TestCase):
    def setUp(self):
        self.store = CommerceHQStoreFactory()
        self.store_shipping_carriers = [{
            'id': 1,
            'title': 'USPS',
            'url': 'https://tools.usps.com/go/TrackConfirmAction_input?qtc_tLabels1=',
            'is_deleted': False
        }, {
            'id': 2,
            'title': 'AfterShip',
            'url': 'http://track.aftership.com/',
            'is_deleted': False
        }]

    @patch('commercehq_core.utils.store_shipping_carriers')
    def test_must_return_shipping_carrier_of_same_name(self, store_shipping_carriers):
        store_shipping_carriers.return_value = self.store_shipping_carriers
        shipping_carrier = get_shipping_carrier('USPS', self.store)
        self.assertEqual(shipping_carrier.get('title'), 'USPS')

    @patch('commercehq_core.utils.store_shipping_carriers')
    def test_must_return_after_ship_if_carrier_is_not_the_same(self, store_shipping_carriers):
        store_shipping_carriers.return_value = self.store_shipping_carriers
        shipping_carrier = get_shipping_carrier('NotInThere', self.store)
        self.assertEqual(shipping_carrier.get('title'), 'AfterShip')

    @patch('commercehq_core.utils.add_aftership_to_store_carriers')
    @patch('commercehq_core.utils.store_shipping_carriers')
    def test_must_add_aftership_if_no_aftership(self, store_shipping_carriers, add_aftership_to_store_carriers):
        aftership = self.store_shipping_carriers.pop()
        store_shipping_carriers.return_value = self.store_shipping_carriers
        add_aftership_to_store_carriers.return_value = aftership
        shipping_carrier = get_shipping_carrier('NotInThere', self.store)
        self.assertEqual(shipping_carrier.get('title'), "AfterShip")


class CheckNotifyCustomerTestCase(TestCase):
    def setUp(self):
        self.invalid_tracking_number = '65141515'

    def test_must_notify_customer(self):
        user_config = {'send_shipping_confirmation': 'yes'}
        notify = check_notify_customer('VALID', user_config, 'USPS')
        self.assertTrue(notify)

    def test_must_not_notify_customer_if_notification_setting_is_off(self):
        user_config = {'send_shipping_confirmation': 'no'}
        notify = check_notify_customer('VALID', user_config, 'USPS')
        self.assertFalse(notify)

    def test_must_not_notify_customer_if_not_valid_and_not_usps(self):
        user_config = {'send_shipping_confirmation': 'yes', 'validate_tracking_number': True}
        notify = check_notify_customer(self.invalid_tracking_number, user_config, 'NOTUSPS')
        self.assertFalse(notify)

    def test_must_notify_customer_if_not_valid_but_usps(self):
        user_config = {'send_shipping_confirmation': 'yes'}
        notify = check_notify_customer(self.invalid_tracking_number, user_config, 'USPS')
        self.assertTrue(notify)

    def test_must_notify_customer_if_validate_is_off(self):
        user_config = {'send_shipping_confirmation': 'yes', 'validate_tracking_number': False}
        notify = check_notify_customer('VALID', user_config, 'NOTUSPS')
        self.assertTrue(notify)

    def test_must_notify_for_default_send_shipping_confirmation_if_last_shipment(self):
        user_config = {'send_shipping_confirmation': 'default', 'validate_tracking_number': False}
        notify = check_notify_customer('VALID', user_config, 'NOTUSPS', last_shipment=True)
        self.assertTrue(notify)

    def test_must_not_notify_for_default_send_shipping_confirmation_if_not_last_shipment(self):
        user_config = {'send_shipping_confirmation': 'default', 'validate_tracking_number': False}
        notify = check_notify_customer('VALID', user_config, 'NOTUSPS', last_shipment=False)
        self.assertFalse(notify)


class AddAftershipToStoreCarriers(TestCase):
    def setUp(self):
        self.store = CommerceHQStoreFactory()
        self.aftership = {
            'id': 2,
            'title': 'AfterShip',
            'url': 'http://track.aftership.com/',
            'is_deleted': False}
        self.response = Mock()
        self.response.raise_for_status = Mock(return_value=None)
        self.response.json = Mock(return_value=self.aftership)

    @patch('commercehq_core.models.CommerceHQStore.request')
    def test_must_add_aftership(self, request):
        request.post = Mock(return_value=self.response)
        shipping_carrier = add_aftership_to_store_carriers(self.store)
        self.assertEqual(shipping_carrier.get('title'), 'AfterShip')


class CacheFulfillmentData(TestCase):
    def setUp(self):
        self.store = CommerceHQStoreFactory()
        self.orders = {
            'items': [{  # Orders
                'id': 1,
                'fulfilments': [{
                    'id': 1,
                    'items': [{
                        'id': 1,
                        'quantity': 2
                    }, {
                        'id': 2,
                        'quantity': 4
                    }]
                }],
                'items': [{  # Order items
                    'data': {
                        'id': 1
                    },
                    'status': {
                        'quantity': 2,
                        'shipped': 4,
                    }
                }, {
                    'data': {
                        'id': 2
                    },
                    'status': {
                        'quantity': 3,
                        'shipped': 5,
                    }
                }]
            }, {
                'id': 2,
                'fulfilments': [{
                    'id': 2,
                    'items': [{
                        'id': 3,
                        'quantity': 3
                    }, {
                        'id': 4,
                        'quantity': 5
                    }]
                }],
                'items': [{
                    'data': {
                        'id': 3
                    },
                    'status': {
                        'quantity': 4,
                        'shipped': 6,
                    }
                }, {
                    'data': {
                        'id': 4
                    },
                    'status': {
                        'quantity': 5,
                        'shipped': 7,
                    }
                }]
            }]
        }

        self.response = Mock()
        self.response.raise_for_status = Mock(return_value=None)
        self.response.json = Mock(return_value=self.orders)

    @patch('commercehq_core.models.CommerceHQStore.request')
    def test_must_cache_order_data(self, request):
        request.post = Mock(return_value=self.response)
        track1 = CommerceHQOrderTrackFactory(store=self.store, order_id=1, line_id=1)
        track2 = CommerceHQOrderTrackFactory(store=self.store, order_id=2, line_id=3)
        tracks = [track1, track2]
        cache_keys = cache_fulfillment_data(tracks)
        self.assertGreaterEqual(len(cache_keys), 12)
        caches['orders'].delete_many(cache_keys)

    @patch('commercehq_core.models.CommerceHQStore.request')
    def test_must_cache_correct_quantity_per_order(self, request):
        request.post = Mock(return_value=self.response)
        track1 = CommerceHQOrderTrackFactory(store=self.store, order_id=1, line_id=1)
        track2 = CommerceHQOrderTrackFactory(store=self.store, order_id=2, line_id=3)
        tracks = [track1, track2]
        cache_keys = cache_fulfillment_data(tracks)
        total1 = caches['orders'].get('chq_total_quantity_{}_{}'.format(self.store.id, 1))
        total2 = caches['orders'].get('chq_total_quantity_{}_{}'.format(self.store.id, 2))
        self.assertEqual(total1, 5)
        self.assertEqual(total2, 9)
        caches['orders'].delete_many(cache_keys)

    @patch('commercehq_core.models.CommerceHQStore.request')
    def test_must_cache_correct_shipped_per_order(self, request):
        request.post = Mock(return_value=self.response)
        track1 = CommerceHQOrderTrackFactory(store=self.store, order_id=1, line_id=1)
        track2 = CommerceHQOrderTrackFactory(store=self.store, order_id=2, line_id=3)
        tracks = [track1, track2]
        cache_keys = cache_fulfillment_data(tracks)
        total1 = caches['orders'].get('chq_total_shipped_{}_{}'.format(self.store.id, 1))
        total2 = caches['orders'].get('chq_total_shipped_{}_{}'.format(self.store.id, 2))
        self.assertEqual(total1, 9)
        self.assertEqual(total2, 13)
        caches['orders'].delete_many(cache_keys)

    @patch('commercehq_core.models.CommerceHQStore.request')
    def test_must_cache_correct_fulfiltment_ids(self, request):
        request.post = Mock(return_value=self.response)
        tracks = [
            CommerceHQOrderTrackFactory(store=self.store, order_id=1, line_id=1),
            CommerceHQOrderTrackFactory(store=self.store, order_id=1, line_id=2),
            CommerceHQOrderTrackFactory(store=self.store, order_id=2, line_id=3),
            CommerceHQOrderTrackFactory(store=self.store, order_id=2, line_id=4),
        ]

        cache_keys = cache_fulfillment_data(tracks)

        fulfilment_ids = [
            caches['orders'].get('chq_fulfilments_{}_{}_{}'.format(self.store.id, 1, 1)),
            caches['orders'].get('chq_fulfilments_{}_{}_{}'.format(self.store.id, 1, 2)),
            caches['orders'].get('chq_fulfilments_{}_{}_{}'.format(self.store.id, 2, 3)),
            caches['orders'].get('chq_fulfilments_{}_{}_{}'.format(self.store.id, 2, 4)),
        ]

        self.assertEqual(fulfilment_ids, [1, 1, 2, 2])
        caches['orders'].delete_many(cache_keys)

    @patch('commercehq_core.models.CommerceHQStore.request')
    def test_must_cache_correct_quantity_ids(self, request):
        request.post = Mock(return_value=self.response)
        tracks = [
            CommerceHQOrderTrackFactory(store=self.store, order_id=1, line_id=1),
            CommerceHQOrderTrackFactory(store=self.store, order_id=1, line_id=2),
            CommerceHQOrderTrackFactory(store=self.store, order_id=2, line_id=3),
            CommerceHQOrderTrackFactory(store=self.store, order_id=2, line_id=4),
        ]

        cache_keys = cache_fulfillment_data(tracks)

        quantities = [
            caches['orders'].get('chq_quantity_{}_{}_{}'.format(self.store.id, 1, 1)),
            caches['orders'].get('chq_quantity_{}_{}_{}'.format(self.store.id, 1, 2)),
            caches['orders'].get('chq_quantity_{}_{}_{}'.format(self.store.id, 2, 3)),
            caches['orders'].get('chq_quantity_{}_{}_{}'.format(self.store.id, 2, 4)),
        ]

        self.assertEqual(sorted(quantities), sorted([2, 4, 3, 5]))
        caches['orders'].delete_many(cache_keys)


class OrdersTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create(username='me', email='me@localhost.com')
        self.store = CommerceHQStore.objects.create(
            user=self.user, title="test1", api_url=CHQ_API_URL,
            api_key=CHQ_API_KEY, api_password=CHQ_API_PASSWORD)

    def test_order_notes(self):
        order_id = 1016
        line_id = 9309669834

        store = self.store
        order = utils.get_chq_order(store, order_id)
        self.assertEqual(order['id'], order_id)

        note1 = 'Test Note #%s' % random_hash()
        utils.set_chq_order_note(store, order_id, note1)

        self.assertEqual(note1, utils.get_chq_order_note(store, order_id))

    def test_order_updater_note(self):
        store = self.store
        order_id = 1015

        note = 'Test Note #%s' % random_hash()

        updater = utils.CHQOrderUpdater(store, order_id)
        updater.add_note(note)
        updater.save_changes(add=False)

        self.assertEqual(note, utils.get_chq_order_note(store, order_id))


class UpdateProductDataImageVariantsTestCase(TestCase):
    def setUp(self):
        self.old_url = 'https://example.com/example.png'
        self.new_url = 'https://example.com/new-image.png'
        self.variant = 'red'
        hashed_ = hash_url_filename(self.old_url)
        data = {'images': [self.old_url], 'variants_images': {hashed_: self.variant}}
        self.product = CommerceHQProductFactory(data=json.dumps(data))

    def test_product_must_have_new_image(self):
        self.product = update_product_data_images(self.product, self.old_url, self.new_url)
        self.assertIn(self.new_url, self.product.parsed.get('images'))

    def test_product_must_not_have_old_image(self):
        self.product = update_product_data_images(self.product, self.old_url, self.new_url)
        self.assertNotIn(self.old_url, self.product.parsed.get('images'))

    def test_product_must_have_new_variant_image(self):
        self.product = update_product_data_images(self.product, self.old_url, self.new_url)
        hashed_new_url = hash_url_filename(self.new_url)
        self.assertIn(hashed_new_url, self.product.parsed.get('variants_images'))

    def test_product_must_not_have_old_variant_image(self):
        self.product = update_product_data_images(self.product, self.old_url, self.new_url)
        hashed_old_url = hash_url_filename(self.old_url)
        self.assertNotIn(hashed_old_url, self.product.parsed.get('variants_images'))

    def test_new_image_must_have_old_image_value(self):
        self.product = update_product_data_images(self.product, self.old_url, self.new_url)
        hashed_new_url = hash_url_filename(self.new_url)
        self.assertEqual(self.product.parsed.get('variants_images')[hashed_new_url], self.variant)
