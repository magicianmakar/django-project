import json

from random import choice
from unittest.mock import patch, Mock, call
from urllib.parse import urlencode

from lib.test import BaseTestCase

from ..utils import (
    WooListQuery,
    woo_customer_address,
    add_product_images_to_api_data,
    get_tracking_products,
)
from .factories import WooStoreFactory, WooProductFactory, WooOrderTrackFactory

from leadgalaxy.tests.factories import UserFactory
from shopified_core.utils import hash_url_filename, update_product_data_images


class WooListQueryTest(BaseTestCase):
    def setUp(self):
        self.response = Mock()
        self.response.raise_for_status = Mock(return_value=None)
        self.response.headers = {'X-WP-Total': 0}
        self.response.json = Mock(return_value=[])
        self.store = WooStoreFactory()

    def test_must_call_api_once(self):
        with patch('woocommerce_core.models.API.get', return_value=self.response) as get:
            query = WooListQuery(self.store, 'test')
            list(query.items())
            list(query.items())
            get.assert_called_once()

    def test_must_call_api_again_if_params_are_updated(self):
        with patch('woocommerce_core.models.API.get', return_value=self.response) as get:
            query = WooListQuery(self.store, 'test')
            list(query.items())
            list(query.update_params({'per_page': 10, 'page': 7}).items())
            self.assertEqual(get.call_count, 2)

    def test_must_call_api_once_to_count_items(self):
        with patch('woocommerce_core.models.API.get', return_value=self.response) as get:
            query = WooListQuery(self.store, 'test')
            list(query.items())
            query.count()
            get.assert_called_once()

    def test_must_call_api_once_to_count_items_twice(self):
        with patch('woocommerce_core.models.API.get', return_value=self.response) as get:
            query = WooListQuery(self.store, 'test')
            query.count()
            query.count()
            get.assert_called_once()


class WooCommerceAddressTest(BaseTestCase):
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
        for value in list(woo_customer_address(self.order)[1].values()):
            self.assertEqual(value, '')


class UpdateProductDataImageVariantsTestCase(BaseTestCase):
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


class TestAddProductImagesToAPIData(BaseTestCase):
    def test_add_using_helper(self):
        test_src = 'https://avatars3.githubusercontent.com/u/36484923?s=60&v=4'
        data = {'images': [test_src]}
        api_data = {}

        add_product_images_to_api_data(api_data, data, user_id=1, from_helper=True)
        self.assertEqual(api_data['images'][0]['name'], test_src)
        self.assertNotEqual(api_data['images'][0]['src'], test_src)

    def test_non_childrens_place(self):
        test_src = 'https://avatars3.githubusercontent.com/u/36484923?s=60&v=4'
        data = {'images': [test_src]}
        api_data = {}

        add_product_images_to_api_data(api_data, data, user_id=1)
        expected = {'src': test_src, 'name': test_src, 'position': 0}
        self.assertDictEqual(api_data['images'][0], expected)

    def test_childrens_place(self):
        test_src = 'http://childrensplace.com/images/product/1111.jpg'
        data = {'images': [test_src]}
        api_data = {}

        s3_src = 'http://s3.jpg'

        with patch('leadgalaxy.utils.upload_file_to_s3', return_value=s3_src):
            add_product_images_to_api_data(api_data, data, user_id=1)

        expected = {'src': s3_src, 'name': s3_src, 'position': 0}
        self.assertDictEqual(api_data['images'][0], expected)


class APIConsumptionTestCase(BaseTestCase):
    def setUp(self):
        self.user = UserFactory()
        self.store = WooStoreFactory(user=self.user)

    @patch('woocommerce.api.API.get')
    def test_calling_once_product_multiple_variations(self, r):
        r.side_effect = [Mock(
            raise_for_status=Mock(return_value=None),
            json=Mock(return_value=[{'id': 1, 'images': []}, {'id': 2, 'images': []}])
        ), Mock(
            raise_for_status=Mock(return_value=None),
            json=Mock(return_value=[
                {'id': 2, 'image': {'src': 'http://example.com/2.jpg'}},
                {'id': 3, 'image': {'src': 'http://example.com/3.jpg'}},
                {'id': 4, 'image': {'src': 'http://example.com/4.jpg'}},
            ])
        ), Mock(
            raise_for_status=Mock(return_value=None),
            json=Mock(return_value=[
                {'id': 2, 'image': {'src': 'http://example.com/2.jpg'}},
                {'id': 3, 'image': {'src': 'http://example.com/3.jpg'}},
                {'id': 4, 'image': {'src': 'http://example.com/4.jpg'}},
            ])
        )]

        tracker_orders = []

        t = WooOrderTrackFactory(product_id=1)
        t.line = {'variation_id': 2}
        tracker_orders.append(t)
        t = WooOrderTrackFactory(product_id=1)
        t.line = {'variation_id': 3}
        tracker_orders.append(t)
        t = WooOrderTrackFactory(product_id=1)
        t.line = {'variation_id': 4}
        tracker_orders.append(t)

        t = WooOrderTrackFactory(product_id=2)
        t.line = {'variation_id': 2}
        tracker_orders.append(t)
        t = WooOrderTrackFactory(product_id=2)
        t.line = {'variation_id': 3}
        tracker_orders.append(t)
        t = WooOrderTrackFactory(product_id=2)
        t.line = {'variation_id': 4}
        tracker_orders.append(t)

        for _ in range(20 - 6):
            tracker = WooOrderTrackFactory(product_id=choice([1, 2]))
            tracker.line = {'variation_id': choice([2, 3, 4])}
            tracker_orders.append(tracker)

        get_tracking_products(self.store, tracker_orders, 50)
        r.assert_has_calls([
            call(f"products?{urlencode({'include': '1,2', 'per_page': '50'})}"),
            call(f"products/1/variations?{urlencode({'include': '2,3,4'})}"),
            call(f"products/2/variations?{urlencode({'include': '2,3,4'})}"),
        ])
