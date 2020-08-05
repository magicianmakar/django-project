import os

from django.conf import settings
from django.core.cache import cache, caches
from django.contrib.auth.models import User
from django.test import tag

from lib.test import BaseTestCase
from unittest.mock import Mock

from collections import OrderedDict
from shopified_core.utils import (
    app_link,
    url_join,
    random_hash,
    prefix_from_model,
    order_data_cache,
    order_phone_number,
    unique_username,
    hash_url_filename,
    encode_params,
    decode_params,
    extension_hash_text,
    get_next_page_from_request,
    normalize_product_title,
    clean_tracking_number
)

from shopified_core.utils import base64_encode
from shopified_core.shipping_helper import (
    country_from_code,
    get_counrties_list,
    fix_br_address,
    fix_fr_address,
    aliexpress_country_code_map,
    CityName,
    valide_aliexpress_province,
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
        self.assertEqual('1205230341.jpg', hash_url_filename('http://g04.a.alicdn.com/kf/HTB18QvDJFXXXXb2XXXQ/Belt-2015-new-arrival-men-which-high.jpg')) # noqa
        self.assertEqual('1384416073.png', hash_url_filename('http://ebay.com/images/UNO-R3-MEGA328P-for-Arduino-Compatible.png?with=450&height=450'))
        self.assertEqual('-1523470574.jpg', hash_url_filename('http://g04.a.alicdn.com/kf/HTB18QvDJFXXXXb2XXXQ/Belt-2015-new-arrival-men-which-high'))
        self.assertEqual('355713761.jpg', hash_url_filename('http://ebay.com/images/UNO-R3-MEGA328P-for-Arduino-Compatible/?with=450&height=450'))
        self.assertEqual('1384415896.jpg', hash_url_filename('http://ebay.com/images/UNO-R3-MEGA328P-for-Arduino-Compatible.php?with=450&height=450'))

        self.assertEqual('677074431.jpg', hash_url_filename(r'https://ae01.alicdn.com/kf/HTB1o9lwPXXXXXbaXFXXq6xXFXXXR/Smael-marke-sportuhr-m%C3%A4nner-' # noqa
                                                            r'digital-led-uhr-military-watch-armee-m%C3%A4nner-armbanduhr-50-mt-wasserdicht-relogio.jpg_50x50.jpg')) # noqa

        self.assertEqual(hash_url_filename('http://g04.a.alicdn.com/kf/HTB18QvDJFXXXXb2XXXQ/Belt-2015-new-arrival-men-which-high.jpg'),
                         hash_url_filename('http://g04.a.alicdn.com/kf/HTB18QvDJFXXXXb2XXXQ/Belt-2015-new-arrival-men-which-high.jpg?with=450&height=450')) # noqa

    def test_hash_url_filename_unicode(self):
        self.assertEqual('1786948925.jpg', hash_url_filename('https://ae01.alicdn.com/kf/HTB1o9lwPXXXXXbaXFXXq6xXFXXXR/Smael-marke-sportuhr-männer-'
                                                             'digital-led-uhr-military-watch-armee-männer-armbanduhr-50-mt-wasserdicht-relogio.jpg_50x50.jpg')) # noqa

        self.assertEqual('-1460244430.jpg', hash_url_filename('https://ae01.alicdn.com/kf/HTB1dvTSHVXXXXX.XFXXq6xXFXXXB/Findking-marke-hohe-'
                                                              'qualität-7-inch-chef-küchenmesser-keramik-messer-gemüse-keramik-messer.jpg_640x640.jpg')) # noqa

        self.assertEqual('677074431.jpg', hash_url_filename(r'https://ae01.alicdn.com/kf/HTB1o9lwPXXXXXbaXFXXq6xXFXXXR/Smael-marke-sportuhr-m'
                                                            r'%C3%A4nner-digital-led-uhr-military-watch-armee-m%C3%A4nner-armbanduhr-50-mt-'
                                                            r'wasserdicht-relogio.jpg_50x50.jpg'))

        self.assertEqual(1628870894, extension_hash_text('New Orange'))
        self.assertEqual(925698, extension_hash_text('灰色'))

    def test_app_link(self):
        self.assertEqual(app_link(), settings.APP_URL)
        self.assertEqual(app_link('orders'), settings.APP_URL + '/orders')
        self.assertEqual(app_link('orders', 'track'), settings.APP_URL + '/orders/track')
        self.assertEqual(app_link('orders/track'), settings.APP_URL + '/orders/track')
        self.assertEqual(app_link('orders', qurey=1001), settings.APP_URL + '/orders?qurey=1001')
        self.assertEqual(app_link('orders', 'place', SAStep=True, product=123456), settings.APP_URL + '/orders/place?SAStep=true&product=123456')

    def test_prefix_from_model(self):
        from leadgalaxy.models import ShopifyStore, GroupPlan, ShopifyProduct
        from commercehq_core.models import CommerceHQProduct
        from groovekart_core.models import GrooveKartProduct
        from woocommerce_core.models import WooProduct
        from bigcommerce_core.models import BigCommerceProduct

        self.assertEqual(prefix_from_model(ShopifyStore()), 'shopify')
        self.assertEqual(prefix_from_model(GroupPlan()), 'shopify')
        self.assertEqual(prefix_from_model(ShopifyProduct()), 'shopify')

        self.assertEqual(prefix_from_model(CommerceHQProduct()), 'chq')

        self.assertEqual(prefix_from_model(GrooveKartProduct()), 'gkart')

        self.assertEqual(prefix_from_model(WooProduct()), 'woo')
        self.assertEqual(prefix_from_model(BigCommerceProduct()), 'bigcommerce')

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
            },
            'woo_order_1_3_111222333': {
                'id': '1_3_111222333',
                'product': 5
            },
            'gear_order_10_30_136622333': {
                'id': '10_30_136622333',
                'product': 5
            },
            'bigcommerce_order_1_3_111222333': {
                'id': '1_3_111222333',
                'product': 5
            },
        }

        caches['orders'].set_many(orders)

        self.assertEqual(order_data_cache(1, 333, 111111), orders['order_1_333_111111'])
        self.assertEqual(order_data_cache('1', '333', '111111'), orders['order_1_333_111111'])

        self.assertEqual(order_data_cache('1_333_111111'), orders['order_1_333_111111'])
        self.assertEqual(order_data_cache('order_1_333_111111'), orders['order_1_333_111111'])

        self.assertEqual(order_data_cache('woo_order', 1, 3, 111222333), orders['woo_order_1_3_111222333'])
        self.assertEqual(order_data_cache('woo_order_1_3_111222333'), orders['woo_order_1_3_111222333'])

        self.assertEqual(order_data_cache('gear_order', 10, 30, 136622333), orders['gear_order_10_30_136622333'])
        self.assertEqual(order_data_cache('gear_order_10_30_136622333'), orders['gear_order_10_30_136622333'])

        self.assertEqual(order_data_cache('bigcommerce_order', 1, 3, 111222333), orders['bigcommerce_order_1_3_111222333'])
        self.assertEqual(order_data_cache('bigcommerce_order_1_3_111222333'), orders['bigcommerce_order_1_3_111222333'])

        self.assertEqual(order_data_cache(1, '222', 444444), orders['order_1_222_444444'])
        self.assertEqual(order_data_cache(3, '222', 444444), None)

        self.assertEqual(list(order_data_cache(1, 333, '*').values()), [orders['order_1_333_111111']])

        data = list(order_data_cache(1, 222, '*').values())
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
        self.assertEqual(decode_params(base64_encode(s)), base64_encode(s))
        self.assertEqual(decode_params(encode_params(s)), s)

        self.assertEqual(decode_params('b:' + base64_encode(s)), s)
        self.assertEqual(encode_params(s), 'b:' + base64_encode(s))

    def test_decode_params_email(self):
        email = 'smith@gmail.com'
        self.assertEqual(decode_params(base64_encode(email)), email)

    def test_decode_params_numbers(self):
        n = '9343'
        self.assertEqual(decode_params(n), n)
        self.assertEqual(decode_params(base64_encode(n)), base64_encode(n))
        self.assertEqual(decode_params(encode_params(n)), n)

        self.assertEqual(decode_params('4624'), '4624')
        self.assertEqual(decode_params('#4624'), '#4624')

    def test_decode_params_names(self):
        s = 'John Smith'
        self.assertEqual(decode_params(s), s)
        self.assertEqual(decode_params(base64_encode(s)), base64_encode(s))
        self.assertEqual(decode_params(encode_params(s)), s)

    def test_decode_params_random(self):
        h = random_hash()
        self.assertEqual(decode_params(h), h)

        h = random_hash()
        self.assertEqual(decode_params(base64_encode(h)), base64_encode(h))

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

    def test_normalize_product_title(self):
        titles = {
            'Allwinner V3s Lqfp128 Quad-core Cpu Processor Chip': 'Allwinner V3s Lqfp128 Quad-core Cpu Processor Chip',
            'Allwinner V3s Lqfp128 Quad-core Cpu On Aliexpress Processor Chip': 'Allwinner V3s Lqfp128 Quad-core Cpu On Processor Chip',
            'Allwinner V3s Lqfp128    Quad-core Cpu Processor Chip -   Avialble in Bulk in Alibaba ': 'Allwinner V3s Lqfp128 Quad-core Cpu Processor Chip - Avialble in Bulk in', # noqa
        }

        suffixes = [
            'Product on Alibaba.com',
            'Product on Alibaba',
            'Product on AliExpress',
            'Product   on   aliexpress.com',
            '- AliExpress',
            '  AliExpress',
            '- aliexpress.com',
            '- Alibaba.com',
            '- Alibaba '
        ]

        for title, match in titles.items():
            for s in suffixes:
                self.assertEqual(normalize_product_title(f'{title} {s}'), match)

    def test_clean_tracking_number(self):
        # Single Tracking number
        self.assertEqual(clean_tracking_number('LC123456789BN'), 'LC123456789BN')
        self.assertEqual(clean_tracking_number('   LC123456789BN   '), 'LC123456789BN')
        self.assertEqual(clean_tracking_number('XC123456789BN\n   '), 'XC123456789BN')

        # Single but duplicate Tracking number
        self.assertEqual(clean_tracking_number('LC123456789BN\nLC123456789BN'), 'LC123456789BN')

        # More than one trackign number
        self.assertEqual(clean_tracking_number('YC123456789BN\nLC123456789CR'), 'YC123456789BN,LC123456789CR')
        self.assertEqual(clean_tracking_number('YC123456789BN\nLC123456789CR\nLC123456789DS'), 'YC123456789BN,LC123456789CR,LC123456789DS')
        self.assertEqual(clean_tracking_number(f'\tRC123456789BN{" " * 10}LC123456789CR\n'), 'RC123456789BN,LC123456789CR')
        self.assertEqual(clean_tracking_number(f'ZC123456789BN{" " * 10}\n{" " * 10}LC123456789CR'), 'ZC123456789BN,LC123456789CR')

        self.assertEqual(clean_tracking_number('YC123456789BN\nLC0000123456789CR'), 'YC123456789BN,LC0000123456789CR')

        # Single Tracking number but splitted in two lines
        self.assertEqual(clean_tracking_number('CNCAI2006110481392 8'), 'CNCAI20061104813928')
        self.assertEqual(clean_tracking_number(f'CNCAI2006110481392{" " * 10}8'), 'CNCAI20061104813928')
        self.assertEqual(clean_tracking_number('CNCAI2006110481392\n8'), 'CNCAI20061104813928')
        self.assertEqual(clean_tracking_number(f'CNCAI2006110481392{" " * 10}\n{" " * 10}8'), 'CNCAI20061104813928')


class ShippingHelperFunctionsTestCase(BaseTestCase):

    def test_fix_br_address(self):
        shipping_address = {'zip': '12345000'}
        modified_address = fix_br_address(shipping_address)
        self.assertEqual(modified_address['zip'], '12345-000')

        shipping_address = {'zip': '12345-000'}
        modified_address = fix_br_address(shipping_address)
        self.assertEqual(modified_address['zip'], '12345-000')

    def test_get_country_from_code(self):
        counrties = {
            'US': 'United States',
            'GB': 'United Kingdom',
            'CA': 'Canada',
        }

        for code, name in list(counrties.items()):
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


class FranceAddressFixTestCase(BaseTestCase):
    def setUp(self):
        cache.delete_pattern('fr_city_*')

    def get_address(self, **kwargs):
        shipping_address = {
            "province": "Paris",
            "city": "Paris",
            "zip": "75019",

            "address1": "Allee Anne-de-Beaujeu N365",
            "address2": "",

            "first_name": "Anna",
            "last_name": "Smith",
            "name": "Anna Smith",
            "province_code": None,
            "phone": "85549863",
            "country_code": "FR",
            "country": "France",
            "company": ""
        }

        shipping_address.update(kwargs)
        return shipping_address

    def get_file_content(self, name):
        return open(os.path.join(settings.BASE_DIR, 'shopified_core/tests/data', name)).read().decode('utf8')

    # @requests_mock.Mocker()
    @tag('slow')
    def test_fix_fr_address(self):
        # m.get('https://geo.api.gouv.fr/communes', text=self.get_file_content('data1.json'))

        shipping_address = self.get_address(
            province="Paris",
            city="Paris",
            zip="75019",
        )

        fixed_address = fix_fr_address(shipping_address)

        self.assertEqual(fixed_address['province'], 'Ile-de-France')
        self.assertEqual(fixed_address['city'], 'Paris')
        self.assertEqual(fixed_address['address2'], '')

    @tag('slow')
    def test_fix_fr_address_zip_match(self):

        shipping_address = self.get_address(
            province="Bourgogne",
            city="nice",
            zip="6300",
        )

        fixed_address = fix_fr_address(shipping_address)

        self.assertEqual(fixed_address['province'], 'Provence-Alpes-Cote d\'Azur')
        self.assertEqual(fixed_address['city'], 'Alpes-Maritimes')
        self.assertEqual(fixed_address['address2'], 'Nice')

    @tag('slow')
    def test_fix_fr_address_paris_arrondissement(self):
        shipping_address = self.get_address(
            province="Paris",
            city="Paris-11E-Arrondissement",
            zip="75011",
        )

        fixed_address = fix_fr_address(shipping_address)

        self.assertEqual(fixed_address['province'], 'Ile-de-France')
        self.assertEqual(fixed_address['city'], 'Paris')
        self.assertEqual(fixed_address['address2'], '')

    @tag('slow')
    def test_fix_fr_address_zip_code_in_city_name(self):

        shipping_address = self.get_address(
            province="Hauts",
            city="59400 - CAMBRAI",
            zip="59400",
        )

        fixed_address = fix_fr_address(shipping_address)

        self.assertEqual(fixed_address['province'], 'Hauts-de-France')
        self.assertEqual(fixed_address['city'], 'Nord')
        self.assertEqual(fixed_address['address2'], 'Cambrai')

    # @requests_mock.Mocker()
    @tag('slow')
    def test_fix_fr_address_multi_occurence(self):
        # m.get('https://geo.api.gouv.fr/communes', text=self.get_file_content('data2.json'))
        shipping_address = self.get_address(
            province="",
            city="courtomer",
            zip="77390",
        )

        fixed_address = fix_fr_address(shipping_address)

        self.assertEqual(fixed_address['province'], 'Ile-de-France')
        self.assertEqual(fixed_address['city'], 'Seine-et-Marne')
        self.assertEqual(fixed_address['address2'], 'Courtomer')

    # @requests_mock.Mocker()
    @tag('slow')
    def test_fix_fr_address_short_common_names(self):
        # m.get('https://geo.api.gouv.fr/communes', text=self.get_file_content('data3.json'))

        shipping_address = self.get_address(
            province="",
            city="Fontaine",
            zip="71150",
            address1="Allee Anne-de-Beaujeu N365",
            address2="5eme Etage N55",
        )

        fixed_address = fix_fr_address(shipping_address)

        self.assertEqual(fixed_address['province'], 'Bourgogne-Franche-Comte')
        self.assertEqual(fixed_address['city'], 'Saone-et-Loire')
        self.assertEqual(fixed_address['address1'], 'Allee Anne-de-Beaujeu N365')
        self.assertEqual(fixed_address['address2'], '5eme Etage N55, Fontaines')

    @tag('slow')
    def test_fix_fr_address_same_zip_and_region(self):

        shipping_address = self.get_address(
            province="",
            city="Villeneuve d'Ornon",
            zip="33140",
            address1="40 rue de Fontenelle",
            address2="Res les 4 platanes Bat E 54",
        )

        fixed_address = fix_fr_address(shipping_address)

        self.assertEqual(fixed_address['province'], 'Nouvelle-Aquitaine')
        self.assertEqual(fixed_address['city'], 'Gironde')
        self.assertEqual(fixed_address['address1'], '40 rue de Fontenelle')
        self.assertEqual(fixed_address['address2'], 'Res les 4 platanes Bat E 54, Villeneuve d\'Ornon')

    @tag('slow')
    def test_fix_fr_address_same_zip_and_region2(self):

        shipping_address = self.get_address(
            province="",
            city="st cricq",
            zip="32430",
            address1="40 rue de Fontenelle",
            address2="",
        )

        fixed_address = fix_fr_address(shipping_address)

        self.assertEqual(fixed_address['province'], 'Occitanie')
        self.assertEqual(fixed_address['city'], 'Gers')
        self.assertEqual(fixed_address['address1'], '40 rue de Fontenelle')
        self.assertEqual(fixed_address['address2'], 'st cricq')


class GetNextPageTest(BaseTestCase):
    def setUp(self):
        self.url = 'https://dev.dropified.com/orders?query_address=US&query_address=GB'
        self.request = Mock(get_raw_uri=Mock(return_value=self.url))

    def test_get_next_page_from_request(self):
        ret_url = get_next_page_from_request(self.request, 1)
        self.assertIn('page=1', ret_url)

        ret_url = get_next_page_from_request(self.request, 3)
        self.assertIn('page=3', ret_url)

    def test_should_have_all_countries_after_page_change(self):
        ret_url = get_next_page_from_request(self.request, 1)
        self.assertIn('query_address=US', ret_url)
        self.assertIn('query_address=GB', ret_url)


class CityNameTestCase(BaseTestCase):
    def test_must_have_name_property(self):
        self.assertEqual(CityName('Saint Louis').name, 'Saint Louis')

    def test_must_return_true_if_starts_with_the_is_true(self):
        self.assertTrue(CityName('The Bronx').starts_with_the)

    def test_without_the_must_return_name_without_leading_the(self):
        self.assertEqual(CityName('The Bronx').without_leading_the, 'Bronx')

    def test_with_other_saint_title_version_must_be_correct_for_st(self):
        self.assertEqual(CityName('St Louis').with_other_saint_title_version, 'Saint Louis')

    def test_with_other_saint_title_version_must_be_correct_for_st_with_dot(self):
        self.assertEqual(CityName('St. Louis').with_other_saint_title_version, 'Saint Louis')

    def test_with_other_saint_title_version_must_be_correct_for_saint(self):
        self.assertEqual(CityName('Saint Louis').with_other_saint_title_version, 'St Louis')

    def test_with_other_saint_title_version_must_be_correct_for_lowercase_st(self):
        self.assertEqual(CityName('st louis').with_other_saint_title_version, 'Saint louis')

    def test_with_other_saint_title_version_must_be_correct_for_lowercase_st_with_dot(self):
        self.assertEqual(CityName('st. louis').with_other_saint_title_version, 'Saint louis')

    def test_with_other_saint_title_version_must_be_correct_for_lowercase_saint(self):
        self.assertEqual(CityName('saint louis').with_other_saint_title_version, 'St louis')

    def test_starting_saint_title_must_be_correct_for_st(self):
        self.assertEqual(CityName('St Louis').starting_saint_title, 'St')

    def test_starting_saint_title_must_be_correct_for_st_with_dot(self):
        self.assertEqual(CityName('St. Louis').starting_saint_title, 'St')

    def test_starting_saint_title_must_be_correct_for_saint(self):
        self.assertEqual(CityName('Saint Louis').starting_saint_title, 'Saint')


class ValideAliExpressProvinceTestCase(BaseTestCase):
    def test_must_correct_cities_with_leading_thes(self):
        valid, correct = valide_aliexpress_province('US', 'New York', 'The Bronx', True)
        self.assertEqual(correct['city'], 'Bronx')

    def test_must_correct_cities_with_st(self):
        valid, correct = valide_aliexpress_province('US', 'Missouri', 'St Louis', True)
        self.assertEqual(correct['city'], 'Saint louis')

    def test_must_correct_cities_with_st_dot(self):
        valid, correct = valide_aliexpress_province('US', 'Missouri', 'St. Louis', True)
        self.assertEqual(correct['city'], 'Saint louis')
