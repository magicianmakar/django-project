from mock import patch, Mock
from requests.exceptions import HTTPError

from django.test import TestCase
from django.core.cache import cache

from .factories import CommerceHQStoreFactory, CommerceHQOrderTrackFactory
from ..utils import (
    get_shipping_carrier,
    check_notify_customer,
    add_aftership_to_store_carriers,
    cache_fulfillment_data,
)


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
        self.invalid_tracking_number = '123456789'

    def test_must_notify_customer(self):
        user_config = {'send_shipping_confirmation': 'yes'}
        notify = check_notify_customer('VALID', user_config, 'USPS')
        self.assertTrue(notify)

    def test_must_not_notify_customer_if_notification_setting_is_off(self):
        user_config = {'send_shipping_confirmation': 'no'}
        notify = check_notify_customer('VALID', user_config, 'USPS')
        self.assertFalse(notify)

    def test_must_not_notify_customer_if_not_valid_and_not_usps(self):
        user_config = {'send_shipping_confirmation': 'yes'}
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
                    'status': {
                        'quantity': 2,
                        'shipped': 4,
                    }
                }, {
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
                    'status': {
                        'quantity': 4,
                        'shipped': 6,
                    }
                }, {
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
        self.assertEqual(len(cache_keys), 8)
        cache.delete_many(cache_keys)

    @patch('commercehq_core.models.CommerceHQStore.request')
    def test_must_cache_correct_quantity_per_order(self, request):
        request.post = Mock(return_value=self.response)
        track1 = CommerceHQOrderTrackFactory(store=self.store, order_id=1, line_id=1)
        track2 = CommerceHQOrderTrackFactory(store=self.store, order_id=2, line_id=3)
        tracks = [track1, track2]
        cache_keys = cache_fulfillment_data(tracks)
        total1 = cache.get('chq_auto_total_quantity_{}_{}'.format(self.store.id, 1))
        total2 = cache.get('chq_auto_total_quantity_{}_{}'.format(self.store.id, 2))
        self.assertEqual(total1, 5)
        self.assertEqual(total2, 9)
        cache.delete_many(cache_keys)

    @patch('commercehq_core.models.CommerceHQStore.request')
    def test_must_cache_correct_shipped_per_order(self, request):
        request.post = Mock(return_value=self.response)
        track1 = CommerceHQOrderTrackFactory(store=self.store, order_id=1, line_id=1)
        track2 = CommerceHQOrderTrackFactory(store=self.store, order_id=2, line_id=3)
        tracks = [track1, track2]
        cache_keys = cache_fulfillment_data(tracks)
        total1 = cache.get('chq_auto_total_shipped_{}_{}'.format(self.store.id, 1))
        total2 = cache.get('chq_auto_total_shipped_{}_{}'.format(self.store.id, 2))
        self.assertEqual(total1, 9)
        self.assertEqual(total2, 13)
        cache.delete_many(cache_keys)

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
            cache.get('chq_auto_fulfilments_{}_{}_{}'.format(self.store.id, 1, 1)),
            cache.get('chq_auto_fulfilments_{}_{}_{}'.format(self.store.id, 1, 2)),
            cache.get('chq_auto_fulfilments_{}_{}_{}'.format(self.store.id, 2, 3)),
            cache.get('chq_auto_fulfilments_{}_{}_{}'.format(self.store.id, 2, 4)),
        ]

        self.assertEqual(fulfilment_ids, [1, 1, 2, 2])
        cache.delete_many(cache_keys)

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
            cache.get('chq_auto_quantity_{}_{}_{}'.format(self.store.id, 1, 1)),
            cache.get('chq_auto_quantity_{}_{}_{}'.format(self.store.id, 1, 2)),
            cache.get('chq_auto_quantity_{}_{}_{}'.format(self.store.id, 2, 3)),
            cache.get('chq_auto_quantity_{}_{}_{}'.format(self.store.id, 2, 4)),
        ]

        self.assertEqual(quantities, [2, 4, 3, 5])
        cache.delete_many(cache_keys)


