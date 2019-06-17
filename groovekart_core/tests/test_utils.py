from unittest.mock import patch

import arrow

from lib.test import BaseTestCase
from django.utils import timezone


from ..utils import (
    get_variant_value,
    get_orders_page_default_date_range,
    update_product_images,
)

from .factories import GrooveKartStoreFactory, GrooveKartProductFactory


class GetVariantValueTestCase(BaseTestCase):
    def test_must_return_dict_for_non_color_values(self):
        label, value = get_variant_value('Size', 'S')
        new_value = {'variant_group_type': 'select', 'variant_name': 'S'}
        self.assertEqual((label, value), ('Size', new_value))

    def test_must_include_color_hash_for_color_label(self):
        label, value = get_variant_value('Color', 'red')
        self.assertIn('color', value)

    def test_must_use_color_for_variant_group_for_color_label(self):
        label, value = get_variant_value('Color', 'red')
        self.assertTrue(value['variant_group_type'], 'color')


class GetOrdersPageDefaultDateRange(BaseTestCase):
    def test_must_start_30_days_from_current_date(self):
        thirty_days_ago = arrow.get(timezone.now()).replace(days=-30).format('MM/DD/YYYY')
        start, end = get_orders_page_default_date_range(timezone)
        self.assertEqual(thirty_days_ago, start)

    def test_must_end_tomorrow_of_current_date(self):
        tomorrow = arrow.get(timezone.now()).replace(days=+1).format('MM/DD/YYYY')
        start, end = get_orders_page_default_date_range(timezone)
        self.assertEqual(tomorrow, end)


class UpdateProductImagesTestCase(BaseTestCase):
    @patch('groovekart_core.models.GrooveKartStoreSession.post')
    def test_must_send_post_request_to_store(self, post_request):
        product = GrooveKartProductFactory(store=GrooveKartStoreFactory())
        images = ['http://test.com/test.jpg']
        update_product_images(product, images)
        self.assertTrue(post_request.called)

    @patch('groovekart_core.models.GrooveKartStoreSession.post')
    def test_must_not_send_post_request_to_store_if_images_is_empty(self, post_request):
        product = GrooveKartProductFactory(store=GrooveKartStoreFactory())
        images = []
        update_product_images(product, images)
        self.assertFalse(post_request.called)

    @patch('groovekart_core.models.GrooveKartStoreSession.post')
    def test_must_not_send_to_store_if_image_is_from_groovekart(self, post_request):
        product = GrooveKartProductFactory(store=GrooveKartStoreFactory())
        images = ['http://groovekart.com/test.jpg']
        update_product_images(product, images)
        self.assertFalse(post_request.called)
