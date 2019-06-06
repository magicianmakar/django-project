import arrow

from lib.test import BaseTestCase
from django.utils import timezone

from ..utils import get_variant_value, get_orders_page_default_date_range


class GetVariantValueTestCase(BaseTestCase):
    def test_must_return_dictionary_for_color_value(self):
        label, value = get_variant_value('Color', 'red')
        self.assertEqual((label, value), ('Color', {'name': 'red'}))

    def test_must_return_string_for_non_color_values(self):
        label, value = get_variant_value('Size', 'S')
        self.assertEqual((label, value), ('Size', 'S'))


class GetOrdersPageDefaultDateRange(BaseTestCase):
    def test_must_start_30_days_from_current_date(self):
        thirty_days_ago = arrow.get(timezone.now()).replace(days=-30).format('MM/DD/YYYY')
        start, end = get_orders_page_default_date_range(timezone)
        self.assertEqual(thirty_days_ago, start)

    def test_must_end_tomorrow_of_current_date(self):
        tomorrow = arrow.get(timezone.now()).replace(days=+1).format('MM/DD/YYYY')
        start, end = get_orders_page_default_date_range(timezone)
        self.assertEqual(tomorrow, end)
