from django.test import TestCase
from mock import Mock

from shopified_core.utils import (
    order_phone_number
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
