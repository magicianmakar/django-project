from mock import patch, Mock

from requests.exceptions import HTTPError

from django.test import TestCase

from ..utils import get_shipping_carrier, check_notify_customer, add_aftership_to_store_carriers
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

    @patch('commercehq_core.utils.add_aftership_to_store_carriers')
    @patch('commercehq_core.utils.store_shipping_carriers')
    def test_must_add_aftership_if_no_aftership(self, store_shipping_carriers, add_aftership_to_store_carriers):
        aftership = self.store_shipping_carriers['items'].pop()
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

    @patch('commercehq_core.models.CommerceHQStore.request')
    def test_must_retry_after_an_error(self, request):
        self.response.raise_for_status = Mock(side_effect=[HTTPError, None])
        request.post = Mock(return_value=self.response)
        shipping_carrier = add_aftership_to_store_carriers(self.store)
        self.assertEqual(shipping_carrier.get('title'), 'AfterShip')

    @patch('commercehq_core.models.CommerceHQStore.request')
    def test_must_retry_after_two_errors(self, request):
        self.response.raise_for_status = Mock(side_effect=[HTTPError, HTTPError, None])
        request.post = Mock(return_value=self.response)
        shipping_carrier = add_aftership_to_store_carriers(self.store)
        self.assertEqual(shipping_carrier.get('title'), 'AfterShip')

    @patch('commercehq_core.models.CommerceHQStore.request')
    def test_must_raise_the_third_error(self, request):
        self.response.raise_for_status = Mock(side_effect=[HTTPError, HTTPError, HTTPError])
        request.post = Mock(return_value=self.response)
        with self.assertRaises(HTTPError):
            add_aftership_to_store_carriers(self.store)
