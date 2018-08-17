import json

from mock import patch, Mock

from django.test import TransactionTestCase

from ..utils import WooListQuery, woo_customer_address
from .factories import WooStoreFactory, WooProductFactory

from shopified_core.utils import hash_url_filename, update_product_data_images


class WooListQueryTest(TransactionTestCase):
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


class WooCommerceAddressTest(TransactionTestCase):
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
            },
            'billing': {
                'address_1': '',
                'address_2': '',
                'city': '',
                'company': '',
                'country': '',
                'first_name': '',
                'last_name': '',
                'postcode': '',
                'state': ''
            },
        }

    def test_must_return_address_even_if_all_values_are_empty_strings(self):
        for value in woo_customer_address(self.order).values():
            self.assertEqual(value, '')


class UpdateProductDataImageVariantsTestCase(TransactionTestCase):
    def setUp(self):
        self.old_url = 'https://example.com/example.png'
        self.new_url = 'https://example.com/new-image.png'
        self.variant = 'red'
        hashed_ = hash_url_filename(self.old_url)
        data = {'images': [self.old_url], 'variants_images': {hashed_: self.variant}}
        self.product = WooProductFactory(data=json.dumps(data))

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
