# -*- coding: utf-8 -*-
import os

from django.conf import settings
from django.test import tag
from lib.test import BaseTestCase
from mock import patch, Mock

from collections import OrderedDict
from django.core.cache import cache, caches
from django.contrib.auth.models import User

from shopified_core.utils import (
    app_link,
    url_join,
    random_hash,
    order_data_cache,
    order_phone_number,
    unique_username,
    hash_url_filename,
    encode_params,
    decode_params,
    extension_hash_text
)

from shopified_core.shipping_helper import (
    country_from_code,
    get_counrties_list,
    aliexpress_country_code_map,
)


class UtilsTestCase(BaseTestCase):
    def setUp(self):
        self.request = Mock(META={'HTTP_X_EXTENSION_VERSION': '1.70.0'})

    def test_order_phone_number(self):
        user = Mock(get_config=Mock(return_value='customer'))

        country_code, phone_number = order_phone_number(self.request, user, '0652413300', 'FR')
        self.assertEqual(country_code, '+33')
        self.assertEqual(phone_number, '652413300')

        country_code, phone_number = order_phone_number(self.request, user, '19716454717', 'ES')
        self.assertEqual(country_code, '+34')
        self.assertEqual(phone_number, '19716454717')

    def test_order_customer_phone_number(self):
        def get_config(name):
            conf = {'order_default_phone': 'customer', 'order_phone_number': '9716454717'}
            return conf.get(name)

        user = Mock(get_config=get_config, profile=Mock(country='ES'))

        country_code, phone_number = order_phone_number(self.request, user, '', 'FR')
        self.assertEqual(country_code, '+34')
        self.assertEqual(phone_number, '9716454717')

    def test_exact_user_phone_number(self):
        def get_config(name):
            conf = {'order_phone_number': '+18889846283'}
            return conf.get(name)

        user = Mock(get_config=get_config, profile=Mock(country='ES'))

        country_code, phone_number = order_phone_number(self.request, user, '', 'FR')
        self.assertEqual(country_code, '+1')
        self.assertEqual(phone_number, '8889846283')

    def test_order_phone_number_pad(self):
        user = Mock(get_config=Mock(return_value='customer'))

        country_code, phone_number = order_phone_number(self.request, user, '0033652413300', 'FR')
        self.assertEqual(country_code, '+33')
        self.assertEqual(phone_number, '652413300')

        country_code, phone_number = order_phone_number(self.request, user, '+33652413300', 'FR')
        self.assertEqual(country_code, '+33')
        self.assertEqual(phone_number, '652413300')

        country_code, phone_number = order_phone_number(self.request, user, '33652413300', 'FR')
        self.assertEqual(country_code, '+33')
        self.assertEqual(phone_number, '652413300')

    def test_empty_order_phone_numbers(self):
        user = Mock(get_config=Mock(return_value='000000000000'))

        country_code, phone_number = order_phone_number(self.request, user, '0652413300', 'US')
        self.assertEqual(country_code, '+1')
        self.assertEqual(phone_number, '000000000000')

        user = Mock(get_config=Mock(return_value='000-0000'))

        country_code, phone_number = order_phone_number(self.request, user, '0652413300', 'US')
        self.assertEqual(country_code, '+1')
        self.assertEqual(phone_number, '0000000')

        user = Mock(get_config=Mock(return_value='000-0000'))

        country_code, phone_number = order_phone_number(self.request, user, '0652413300', 'AU')
        self.assertEqual(country_code, '+61')
        self.assertEqual(phone_number, '0000000')

        country_code, phone_number = order_phone_number(self.request, user, '0652413300', '')
        self.assertEqual(country_code, '+1')
        self.assertEqual(phone_number, '0000000')

    def test_null_order_phone_numbers(self):
        user = Mock(get_config=Mock(return_value='customer'))

        country_code, phone_number = order_phone_number(self.request, user, None, 'US')
        self.assertEqual(country_code, '+1')
        self.assertEqual(phone_number, '')

    def test_chase_phone_numbers(self):
        def get_config(name):
            conf = {'order_phone_number': '+1-2056577766'}
            return conf.get(name)

        user = Mock(get_config=get_config, profile=Mock(country='ES'))

        country_code, phone_number = order_phone_number(self.request, user, '', 'FR')
        # self.assertEqual(country_code, '+1')
        self.assertEqual(phone_number, '0000000000')


    def test_chase_phone_numbers_by_chase(self):
        def get_config(name):
            conf = {'order_phone_number': '+1-2056577766'}
            return conf.get(name)

        user = Mock(get_config=get_config, profile=Mock(country='ES'), username='chase')
        user.models_user = user

        country_code, phone_number = order_phone_number(self.request, user, '', 'FR')
        # self.assertEqual(country_code, '+1')
        self.assertEqual(phone_number, '2056577766')

    def test_hash_url_filename(self):
        self.assertEqual('1205230341.jpg', hash_url_filename('http://g04.a.alicdn.com/kf/HTB18QvDJFXXXXb2XXXQ/Belt-2015-new-arrival-men-which-high.jpg'))
        self.assertEqual('1384416073.png', hash_url_filename('http://ebay.com/images/UNO-R3-MEGA328P-for-Arduino-Compatible.png?with=450&height=450'))
        self.assertEqual('-1523470574.jpg', hash_url_filename('http://g04.a.alicdn.com/kf/HTB18QvDJFXXXXb2XXXQ/Belt-2015-new-arrival-men-which-high'))
        self.assertEqual('355713761.jpg', hash_url_filename('http://ebay.com/images/UNO-R3-MEGA328P-for-Arduino-Compatible/?with=450&height=450'))
        self.assertEqual('1384415896.jpg', hash_url_filename('http://ebay.com/images/UNO-R3-MEGA328P-for-Arduino-Compatible.php?with=450&height=450'))

        self.assertEqual('677074431.jpg', hash_url_filename(r'https://ae01.alicdn.com/kf/HTB1o9lwPXXXXXbaXFXXq6xXFXXXR/Smael-marke-sportuhr-m%C3%A4nner-'
                                                            r'digital-led-uhr-military-watch-armee-m%C3%A4nner-armbanduhr-50-mt-wasserdicht-relogio.jpg_50x50.jpg'))

        self.assertEqual(hash_url_filename('http://g04.a.alicdn.com/kf/HTB18QvDJFXXXXb2XXXQ/Belt-2015-new-arrival-men-which-high.jpg'),
                         hash_url_filename('http://g04.a.alicdn.com/kf/HTB18QvDJFXXXXb2XXXQ/Belt-2015-new-arrival-men-which-high.jpg?with=450&height=450'))

    def test_hash_url_filename_unicode(self):
        self.assertEqual('1786948925.jpg', hash_url_filename(u'https://ae01.alicdn.com/kf/HTB1o9lwPXXXXXbaXFXXq6xXFXXXR/Smael-marke-sportuhr-männer-'
                                                             u'digital-led-uhr-military-watch-armee-männer-armbanduhr-50-mt-wasserdicht-relogio.jpg_50x50.jpg'))

        self.assertEqual('-1460244430.jpg', hash_url_filename(u'https://ae01.alicdn.com/kf/HTB1dvTSHVXXXXX.XFXXq6xXFXXXB/Findking-marke-hohe-'
                                                              u'qualität-7-inch-chef-küchenmesser-keramik-messer-gemüse-keramik-messer.jpg_640x640.jpg'))

        self.assertEqual('677074431.jpg', hash_url_filename(r'https://ae01.alicdn.com/kf/HTB1o9lwPXXXXXbaXFXXq6xXFXXXR/Smael-marke-sportuhr-m'
                                                            r'%C3%A4nner-digital-led-uhr-military-watch-armee-m%C3%A4nner-armbanduhr-50-mt-'
                                                            r'wasserdicht-relogio.jpg_50x50.jpg'))

        self.assertEqual(1628870894, extension_hash_text(u'New Orange'))
        self.assertEqual(925698, extension_hash_text(u'灰色'))

    def test_app_link(self):
        self.assertEqual(app_link(), settings.APP_URL)
        self.assertEqual(app_link('orders'), settings.APP_URL + '/orders')
        self.assertEqual(app_link('orders', 'track'), settings.APP_URL + '/orders/track')
        self.assertEqual(app_link('orders/track'), settings.APP_URL + '/orders/track')
        self.assertEqual(app_link('orders', qurey=1001), settings.APP_URL + '/orders?qurey=1001')
        self.assertEqual(app_link('orders', 'place', SAStep=True, product=123456), settings.APP_URL + '/orders/place?SAStep=true&product=123456')

    def test_order_data(self):
        orders = {
            'order_1_222_333333': {
                'id': '1_222_333333',
                'product': 3
            },
            'order_1_222_444444': {
                'id': '1_222_44444',
                'product': 4
            },
            'order_1_333_111111': {
                'id': '1_333_111111',
                'product': 5
            }
        }

        caches['orders'].set_many(orders)

        self.assertEqual(order_data_cache(1, 333, 111111), orders['order_1_333_111111'])
        self.assertEqual(order_data_cache('1', '333', '111111'), orders['order_1_333_111111'])

        self.assertEqual(order_data_cache('1_333_111111'), orders['order_1_333_111111'])
        self.assertEqual(order_data_cache('order_1_333_111111'), orders['order_1_333_111111'])

        self.assertEqual(order_data_cache(1, '222', 444444), orders['order_1_222_444444'])
        self.assertEqual(order_data_cache(3, '222', 444444), None)

        self.assertEqual(order_data_cache(1, 333, '*').values(), [orders['order_1_333_111111']])

        data = order_data_cache(1, 222, '*').values()
        self.assertEqual(len(data), 2)
        self.assertIn(data[0], [orders['order_1_222_333333'], orders['order_1_222_444444']])
        self.assertIn(data[1], [orders['order_1_222_333333'], orders['order_1_222_444444']])

    def test_unique_username(self):
        username = unique_username()
        self.assertEqual(username, 'user')
        User.objects.create(username=username)

        username = unique_username()
        self.assertEqual(username, 'user1')
        User.objects.create(username=username)

        username = unique_username('john')
        self.assertEqual(username, 'john')
        User.objects.create(username=username)

        username = unique_username('john@example.com')
        self.assertEqual(username, 'john1')
        User.objects.create(username=username)

        username = unique_username('John@example.com')
        self.assertEqual(username, 'john2')
        User.objects.create(username=username)

        username = unique_username('John')
        self.assertEqual(username, 'john3')
        User.objects.create(username=username)

        for i in range(30):
            username = unique_username('john')
            self.assertEqual(username, 'john%d' % (4 + i))
            User.objects.create(username=username)

    def test_unique_username_fullname(self):
        username = unique_username('john', fullname="John Smith")
        self.assertEqual(username, 'john')
        User.objects.create(username=username)

        username = unique_username('john', fullname="John Smith")
        self.assertEqual(username, 'john.smith')

        username = unique_username('john', fullname="John & Smith")
        self.assertEqual(username, 'john.smith')

        User.objects.create(username='john.smith')

        username = unique_username('john', fullname="John & Smith")
        self.assertEqual(username, 'john.smith1')
        User.objects.create(username=username)

        username = unique_username('john', fullname=['John', 'Smith'])
        self.assertEqual(username, 'john.smith2')

        username = unique_username('john2', fullname=[])
        self.assertEqual(username, 'john2')

        username = unique_username('john2', fullname=[' '])
        self.assertEqual(username, 'john2')

        username = unique_username('john2', fullname=[' ', ' '])
        self.assertEqual(username, 'john2')

        username = unique_username('john2', fullname=[''])
        self.assertEqual(username, 'john2')

        username = unique_username('john2', fullname=['A', 'B'])
        self.assertEqual(username, 'john2')

        username = unique_username('', fullname=[])
        self.assertEqual(username, 'user')

    def test_unique_username_long_name(self):
        username = unique_username('', fullname='Thiago Reges Rodrigues De Souza')
        self.assertTrue(len(username) <= 30)
        User.objects.create(username=username)

        username = unique_username('', fullname='Thiago Reges Rodrigues De Souza')
        self.assertTrue(len(username) <= 30)

        username = unique_username('', fullname='Thiago Reges Rodrigues De Souza De Rodrigues De Reges')
        self.assertTrue(len(username) <= 30)
        User.objects.create(username=username)

        username = unique_username('', fullname='Thiago Reges Rodrigues De Souza De Rodrigues De Reges')
        self.assertTrue(len(username) <= 30)
        User.objects.create(username=username)

        username = unique_username('', fullname='Thiago Reges Rodrigues De Souza De Rodrigues De Reges')
        self.assertTrue(len(username) <= 30)

    def test_decode_params_str(self):
        s = 'test'
        self.assertEqual(decode_params(s), s)
        self.assertEqual(decode_params(s.encode('base64')), s.encode('base64'))
        self.assertEqual(decode_params(encode_params(s)), s)

        self.assertEqual(decode_params('b:' + s.encode('base64')), s)
        self.assertEqual(encode_params(s), 'b:' + s.encode('base64').strip())

    def test_decode_params_email(self):
        email = 'smith@gmail.com'
        self.assertEqual(decode_params(email.encode('base64')), email)

    def test_decode_params_numbers(self):
        n = '9343'
        self.assertEqual(decode_params(n), n)
        self.assertEqual(decode_params(n.encode('base64')), n.encode('base64'))
        self.assertEqual(decode_params(encode_params(n)), n)

        self.assertEqual(decode_params('4624'), '4624')
        self.assertEqual(decode_params('#4624'), '#4624')

    def test_decode_params_names(self):
        s = 'John Smith'
        self.assertEqual(decode_params(s), s)
        self.assertEqual(decode_params(s.encode('base64')), s.encode('base64'))
        self.assertEqual(decode_params(encode_params(s)), s)

    def test_decode_params_random(self):
        h = random_hash()
        self.assertEqual(decode_params(h), h)

        h = random_hash()
        self.assertEqual(decode_params(h.encode('base64')), h.encode('base64'))

        h = random_hash()
        self.assertEqual(decode_params(encode_params(h)), h)

    def test_url_join(self):
        base_url = 'https://price-monitor-api.herokuapp.com'
        self.assertEqual(url_join('/api/products/price', 12, '3/2/'), 'api/products/price/12/3/2')
        self.assertEqual(url_join('api/products/price', 12, '3/2'), 'api/products/price/12/3/2')

        self.assertEqual(url_join('http://app.dropified.com/', 'api/products/price', 12, '3/2'), 'http://app.dropified.com/api/products/price/12/3/2')

        self.assertEqual(url_join(base_url), base_url)
        self.assertEqual(url_join(base_url, '/'), base_url)

        self.assertEqual(url_join(base_url, '/api/products'), base_url + '/api/products')
        self.assertEqual(url_join(base_url, '/api/products/'), base_url + '/api/products')
        self.assertEqual(url_join(base_url, '/api/products', 233330), base_url + '/api/products/233330')
        self.assertEqual(url_join(base_url, '/api/products', 233330, '/'), base_url + '/api/products/233330')
        self.assertEqual(url_join(base_url, '/api/products', 233330, '/variants'), base_url + '/api/products/233330/variants')
        self.assertEqual(url_join(base_url, 'api/products', 233330, '/variants'), base_url + '/api/products/233330/variants')

        self.assertEqual(url_join(base_url, 'api', 'products', 233330, '/variants'), base_url + '/api/products/233330/variants')


class ShippingHelperFunctionsTestCase(BaseTestCase):

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

    def test_aliexpress_country_code_map(self):
        self.assertEqual(aliexpress_country_code_map('UK'), 'UK')
        self.assertEqual(aliexpress_country_code_map('GB'), 'UK')
        self.assertEqual(aliexpress_country_code_map('ME'), 'MNE')
        self.assertEqual(aliexpress_country_code_map('US'), 'US')
