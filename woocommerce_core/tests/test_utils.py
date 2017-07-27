from mock import patch, Mock

from django.test import TestCase

from ..utils import WooListQuery
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
