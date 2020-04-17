import json

from unittest.mock import patch, Mock

from lib.test import BaseTestCase

from ..utils import (
    BigCommerceListQuery,
    bigcommerce_customer_address,
    add_product_images_to_api_data,
)
from .factories import BigCommerceStoreFactory, BigCommerceProductFactory

from shopified_core.utils import hash_url_filename, update_product_data_images


class BigCommerceListQueryTest(BaseTestCase):
    def setUp(self):
        self.response = Mock()
        self.response.raise_for_status = Mock(return_value=None)
        self.response.headers = {'X-WP-Total': 0}
        self.response.json = Mock(return_value=[])
        self.store = BigCommerceStoreFactory()

    def test_must_call_api_once(self):
        with patch.object(self.store.request, 'get', return_value=self.response) as get:
            query = BigCommerceListQuery(self.store, 'test')
            list(query.items())
            list(query.items())
            get.assert_called_once()

    def test_must_call_api_again_if_params_are_updated(self):
        with patch.object(self.store.request, 'get', return_value=self.response) as get:
            query = BigCommerceListQuery(self.store, 'test')
            list(query.items())
            list(query.update_params({'per_page': 10, 'page': 7}).items())
            self.assertEqual(get.call_count, 2)

    def test_must_call_api_once_to_count_items(self):
        with patch.object(self.store.request, 'get', return_value=self.response) as get:
            query = BigCommerceListQuery(self.store, 'test')
            list(query.items())
            query.count()
            get.assert_called()

    def test_must_call_api_once_to_count_items_twice(self):
        with patch.object(self.store.request, 'get', return_value=self.response) as get:
            query = BigCommerceListQuery(self.store, 'test')
            query.count()
            query.count()
            get.assert_called()


class BigCommerceAddressTest(BaseTestCase):
    def setUp(self):
        self.order = {
            'shipping_addresses': [{
                'street_1': '',
                'street_2': '',
                'city': '',
                'company': '',
                'country': '',
                'country_iso2': '',
                'first_name': '',
                'last_name': '',
                'zip': '',
                'state': ''
            }],
            'billing_address': {
                'street_1': '',
                'street_2': '',
                'city': '',
                'company': '',
                'country': '',
                'country_iso2': '',
                'first_name': '',
                'last_name': '',
                'zip': '',
                'state': ''
            },
        }

    def test_must_return_address_even_if_all_values_are_empty_strings(self):
        for value in list(bigcommerce_customer_address(self.order)[1].values()):
            self.assertEqual(value, '')


class UpdateProductDataImageVariantsTestCase(BaseTestCase):
    def setUp(self):
        self.old_url = 'https://example.com/example.png'
        self.new_url = 'https://example.com/new-image.png'
        self.variant = 'red'
        hashed_ = hash_url_filename(self.old_url)
        data = {'images': [self.old_url], 'variants_images': {hashed_: self.variant}}
        self.product = BigCommerceProductFactory(data=json.dumps(data))

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


class TestAddProductImagesToAPIData(BaseTestCase):
    def test_non_childrens_place(self):
        test_src = 'https://avatars3.githubusercontent.com/u/36484923?s=60&v=4'
        data = {'images': [test_src]}
        api_data = {}

        add_product_images_to_api_data(api_data, data)
        expected = {'image_url': test_src, 'is_thumbnail': True}
        self.assertDictEqual(api_data['images'][0], expected)
