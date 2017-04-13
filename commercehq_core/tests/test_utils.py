from mock import patch

from django.test import TestCase

from ..utils import get_shipping_carrier, should_notify_customer
from .factories import CommerceHQStoreFactory


class GetShippingCarrierTestCase(TestCase):
    def setUp(self):
        self.store = CommerceHQStoreFactory()
        self.store_shipping_carriers = {
            'items': [{
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
        }

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

    @patch('commercehq_core.utils.store_shipping_carriers')
    def test_must_return_none_if_carrier_no_aftership(self, store_shipping_carriers):
        self.store_shipping_carriers['items'].pop()
        store_shipping_carriers.return_value = self.store_shipping_carriers
        shipping_carrier = get_shipping_carrier('NotInThere', self.store)
        self.assertEqual(shipping_carrier.get('title'), None)


class ShouldNotifyCustomerTestCase(TestCase):
    def setUp(self):
        self.invalid_tracking_number = '123456789'

    def test_must_notify_customer(self):
        user_config = {'send_shipping_confirmation': 'yes'}
        notify = should_notify_customer('VALID', user_config, 'USPS')
        self.assertTrue(notify)

    def test_must_not_notify_customer_if_notification_setting_is_off(self):
        user_config = {'send_shipping_confirmation': 'no'}
        notify = should_notify_customer('VALID', user_config, 'USPS')
        self.assertFalse(notify)

    def test_must_not_notify_customer_if_not_valid_and_not_usps(self):
        user_config = {'send_shipping_confirmation': 'yes'}
        notify = should_notify_customer(self.invalid_tracking_number, user_config, 'NOTUSPS')
        self.assertFalse(notify)

    def test_must_notify_customer_if_not_valid_but_usps(self):
        user_config = {'send_shipping_confirmation': 'yes'}
        notify = should_notify_customer(self.invalid_tracking_number, user_config, 'USPS')
        self.assertTrue(notify)

    def test_must_notify_customer_if_validate_is_off(self):
        user_config = {'send_shipping_confirmation': 'yes', 'validate_tracking_number': False}
        notify = should_notify_customer('VALID', user_config, 'NOTUSPS')
        self.assertTrue(notify)

