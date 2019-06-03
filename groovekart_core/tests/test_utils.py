from lib.test import BaseTestCase

from ..utils import get_variant_value


class GetVariantValueTestCase(BaseTestCase):
    def test_must_return_dictionary_for_color_value(self):
        label, value = get_variant_value('Color', 'red')
        self.assertEqual((label, value), ('Color', {'name': 'red'}))

    def test_must_return_string_for_non_color_values(self):
        label, value = get_variant_value('Size', 'S')
        self.assertEqual((label, value), ('Size', 'S'))
