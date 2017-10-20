from mock import patch, Mock

from django.test import TestCase

from ..utils import WooListQuery, woo_customer_address
from .factories import WooStoreFactory


class WooListQueryTest(TestCase):
    def setUp(self):
        self.response = Mock()
        self.response.raise_for_status = Mock(return_value=None)
        self.response.headers = {'X-WP-Total': 0}
        self.response.json = Mock(return_value=[])
        self.store = WooStoreFactory()

    def test_must_call_api_once(self):
        with patch('woocommerce_core.models.API.get', return_value=self.response) as get:
            query = WooListQuery(self.store, 'test')
            query.items()
            query.items()
            get.assert_called_once()

    def test_must_call_api_again_if_params_are_updated(self):
        with patch('woocommerce_core.models.API.get', return_value=self.response) as get:
            query = WooListQuery(self.store, 'test')
            query.items()
            query.update_params({'per_page': 10, 'page': 7}).items()
            self.assertEqual(get.call_count, 2)

    def test_must_call_api_once_to_count_items(self):
        with patch('woocommerce_core.models.API.get', return_value=self.response) as get:
            query = WooListQuery(self.store, 'test')
            query.items()
            query.count()
            get.assert_called_once()

    def test_must_call_api_once_to_count_items_twice(self):
        with patch('woocommerce_core.models.API.get', return_value=self.response) as get:
            query = WooListQuery(self.store, 'test')
            query.count()
            query.count()
            get.assert_called_once()


class WooCommerceAddressTest(TestCase):
    def setUp(self):
        self.order = {
            'shipping': {
                'address_1': '',
                'address_2': '',
                'city': '',
                'company': '',
                'country': '',
                'first_name': '',
                'last_name': '',
                'postcode': '',
                'state': ''
            }
        }

    def test_must_return_address_even_if_all_values_are_empty_strings(self):
        for value in woo_customer_address(self.order).values():
            self.assertEqual(value, '')
