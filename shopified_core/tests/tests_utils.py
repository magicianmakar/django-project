from django.test import TestCase
from mock import Mock
from collections import OrderedDict

from shopified_core.utils import (
    order_phone_number
)

from shopified_core.shipping_helper import (
    country_from_code,
    get_counrties_list
)


class UtilsTestCase(TestCase):
    def setUp(self):
        pass

    def test_old_order_phone_number(self):
        user = Mock(get_config=Mock(return_value='customer'))
        request = Mock(META={'HTTP_X_EXTENSION_VERSION': '1.61.5'})

        country_code, phone_number = order_phone_number(request, user, '0652413300', 'FR')
        self.assertEqual(country_code, None)
        self.assertEqual(phone_number, '0652413300')

    def test_order_phone_number(self):
        user = Mock(get_config=Mock(return_value='customer'))
        request = Mock(META={'HTTP_X_EXTENSION_VERSION': '1.70.0'})

        country_code, phone_number = order_phone_number(request, user, '0652413300', 'FR')
        self.assertEqual(country_code, '+33')
        self.assertEqual(phone_number, '652413300')

    def test_order_phone_number_pad(self):
        user = Mock(get_config=Mock(return_value='customer'))
        request = Mock(META={'HTTP_X_EXTENSION_VERSION': '1.70.0'})

        country_code, phone_number = order_phone_number(request, user, '0033652413300', 'FR')
        self.assertEqual(country_code, '+33')
        self.assertEqual(phone_number, '652413300')

        country_code, phone_number = order_phone_number(request, user, '+33652413300', 'FR')
        self.assertEqual(country_code, '+33')
        self.assertEqual(phone_number, '652413300')

        country_code, phone_number = order_phone_number(request, user, '33652413300', 'FR')
        self.assertEqual(country_code, '+33')
        self.assertEqual(phone_number, '652413300')

    def test_empty_order_phone_numbers(self):
        user = Mock(get_config=Mock(return_value='000000000000'))
        request = Mock(META={'HTTP_X_EXTENSION_VERSION': '1.62.0'})

        country_code, phone_number = order_phone_number(request, user, '0652413300', 'US')
        self.assertEqual(country_code, '+1')
        self.assertEqual(phone_number, '000000000000')

        user = Mock(get_config=Mock(return_value='000-0000'))
        request = Mock(META={'HTTP_X_EXTENSION_VERSION': '1.62.0'})

        country_code, phone_number = order_phone_number(request, user, '0652413300', 'US')
        self.assertEqual(country_code, '+1')
        self.assertEqual(phone_number, '0000000')

        user = Mock(get_config=Mock(return_value='000-0000'))
        request = Mock(META={'HTTP_X_EXTENSION_VERSION': '1.62.0'})

        country_code, phone_number = order_phone_number(request, user, '0652413300', 'AU')
        self.assertEqual(country_code, '+61')
        self.assertEqual(phone_number, '0000000')

        country_code, phone_number = order_phone_number(request, user, '0652413300', '')
        self.assertEqual(country_code, '+1')
        self.assertEqual(phone_number, '0000000')

    def test_null_order_phone_numbers(self):
        user = Mock(get_config=Mock(return_value='customer'))
        request = Mock(META={'HTTP_X_EXTENSION_VERSION': '1.62.0'})

        country_code, phone_number = order_phone_number(request, user, None, 'US')
        self.assertEqual(country_code, '+1')
        self.assertEqual(phone_number, '')


class ShippingHelperTestCase(TestCase):
    def setUp(self):
        pass

    def test_get_country_from_code(self):
        counrties = {
            'US': 'United States',
            'GB': 'United Kingdom',
            'CA': 'Canada',
        }

        for code, name in counrties.items():
            self.assertEqual(country_from_code(code), name)

    def test_get_country_list(self):
        counrties = OrderedDict()
        counrties['US'] = 'United States'
        counrties['GB'] = 'United Kingdom'
        counrties['CA'] = 'Canada'

        counrties_list = get_counrties_list()

        for i, c in enumerate(counrties.items()):
            self.assertEqual(counrties_list[i][0], c[0])
