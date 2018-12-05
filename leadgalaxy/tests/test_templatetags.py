from lib.test import BaseTestCase

from mock import Mock

from leadgalaxy.templatetags import template_helper


class TagsTestCase(BaseTestCase):
    def setUp(self):
        pass

    def test_shopify_image(self):
        self.assertEqual(template_helper.shopify_image_thumb(
            'https://cdn.shopify.com/s/files/1/1013/1174/products/HTB1v0vzIVXXXXb8XFXXq6xXFXXXd.jpg?v=1445304129'),
            'https://cdn.shopify.com/s/files/1/1013/1174/products/HTB1v0vzIVXXXXb8XFXXq6xXFXXXd_small.jpg?v=1445304129')

        self.assertEqual(template_helper.shopify_image_thumb(
            'https://cdn.shopify.com/s/files/1/1013/1174/products/v-C01__AOFLY-72e4-44c0-8ca3-3f9272346bfc.jpg?v=1463296088'),
            'https://cdn.shopify.com/s/files/1/1013/1174/products/v-C01__AOFLY-72e4-44c0-8ca3-3f9272346bfc_small.jpg?v=1463296088')

        self.assertEqual(template_helper.shopify_image_thumb(
            'https://cdn.shopify.com/s/files/1/1013/1174/products/Mini-Camping-Travel-Fish-Pen-Fishing-Rod-Pole-Reel-No-Shipping-Fee-K5BO.jpg_350x350.jpg?v=1445235680'),
            'https://cdn.shopify.com/s/files/1/1013/1174/products/Mini-Camping-Travel-Fish-Pen-Fishing-Rod-Pole-Reel-No-Shipping-Fee-K5BO.jpg_350x350_small.jpg?v=1445235680')

        self.assertEqual(template_helper.shopify_image_thumb(
            'https://cdn.shopify.com/s/files/1/1013/1174/products/2015-Hot-Selling-European-And-American-Popular-Hunger-Games-Mock-Bird-LOGO-Necklace_6314c7f9-4ec8-4397-aaac-6a7b080cf1ed.jpeg?v=1454342022'),
            'https://cdn.shopify.com/s/files/1/1013/1174/products/2015-Hot-Selling-European-And-American-Popular-Hunger-Games-Mock-Bird-LOGO-Necklace_6314c7f9-4ec8-4397-aaac-6a7b080cf1ed_small.jpeg?v=1454342022')

        self.assertEqual(template_helper.shopify_image_thumb(
            'https://cdn.shopify.com/s/files/1/1341/0283/products/FF_A.gif?v=1466355079'),
            'https://cdn.shopify.com/s/files/1/1341/0283/products/FF_A_small.gif?v=1466355079')

    def test_shopify_image_size(self):
        self.assertEqual(template_helper.shopify_image_thumb(
            'https://cdn.shopify.com/s/files/1/1013/1174/products/HTB1v0vzIVXXXXb8XFXXq6xXFXXXd.jpg?v=1445304129', size='thumb'),
            'https://cdn.shopify.com/s/files/1/1013/1174/products/HTB1v0vzIVXXXXb8XFXXq6xXFXXXd_thumb.jpg?v=1445304129')

        self.assertEqual(template_helper.shopify_image_thumb(
            'https://cdn.shopify.com/s/files/1/1013/1174/products/HTB1v0vzIVXXXXb8XFXXq6xXFXXXd.jpg?v=1445304129', size='64x64'),
            'https://cdn.shopify.com/s/files/1/1013/1174/products/HTB1v0vzIVXXXXb8XFXXq6xXFXXXd_64x64.jpg?v=1445304129')

    def test_shopify_image_crop(self):
        self.assertEqual(template_helper.shopify_image_thumb(
            'https://cdn.shopify.com/s/files/1/1013/1174/products/HTB1v0vzIVXXXXb8XFXXq6xXFXXXd.jpg?v=1445304129', size='thumb', crop='center'),
            'https://cdn.shopify.com/s/files/1/1013/1174/products/HTB1v0vzIVXXXXb8XFXXq6xXFXXXd_thumb_crop_center.jpg?v=1445304129')

        self.assertEqual(template_helper.shopify_image_thumb(
            'https://cdn.shopify.com/s/files/1/1013/1174/products/HTB1v0vzIVXXXXb8XFXXq6xXFXXXd.jpg?v=1445304129', size='64x64', crop='center'),
            'https://cdn.shopify.com/s/files/1/1013/1174/products/HTB1v0vzIVXXXXb8XFXXq6xXFXXXd_64x64_crop_center.jpg?v=1445304129')

    def test_shopify_image_obj_path(self):
        img = ('https://s3-us-west-2.amazonaws.com/commercehq-userfiles-master/commercehq-store29857086'
               '/uploads/1489910485_59ef386e8d0880257db38f529394b4f3bb4ad05b.jpg')

        obj = {
            'id': 298,
            'max_size': 8,
            'path': img
        }

        self.assertEqual(template_helper.shopify_image_thumb(obj), img)

    def test_shopify_image_obj_src(self):
        img = ("https://cdn.shopify.com/s/files/1/1013/1174/products/5000-mah-Battery-Everycom-S6-plus-"
               "mini-phone-projector-dlp-wifi-portable-Handheld-smartphone-Projector-Android_a728ca1f-"
               "3ee1-4d7a-bad7-4db9b2be7260.jpg?v=1478952978")

        obj = {
            "position": 1,
            "src": img,
            "updated_at": "2016-11-12T06:16:18-06:00",
            "variant_ids": []
        }

        self.assertEqual(template_helper.shopify_image_thumb(obj), img.replace('4db9b2be7260.jpg', '4db9b2be7260_small.jpg'))

    def test_money_format(self):
        store = Mock()
        store.currency_format = "${{amount}}"

        self.assertEqual(template_helper.money_format(12.34, store), '$12.34')
        self.assertEqual(template_helper.money_format(1000.10, store), '$1,000.10')
        self.assertEqual(template_helper.money_format(-1000.10, store), '- $1,000.10')

        self.assertEqual(template_helper.money_format(0, store), '$0.00')
        self.assertEqual(template_helper.money_format(0.0, store), '$0.00')
        self.assertEqual(template_helper.money_format(0.0, store), '$0.00')

        self.assertEqual(template_helper.money_format(None, store), '$')
        self.assertEqual(template_helper.money_format(None, None), '$')
        self.assertEqual(template_helper.money_format('', None), '$')
        self.assertEqual(template_helper.money_format('', store), '$')

    def test_money_format_euro(self):
        store = Mock()
        store.currency_format = u"\u20ac {{amount}}"
        self.assertEqual(template_helper.money_format(12.34, store), u'\u20ac 12.34')

    def test_money_format_amount_no_decimals(self):
        store = Mock()
        store.currency_format = "${{amount_no_decimals}}"

        self.assertEqual(template_helper.money_format(12.34, store), '$12')
        self.assertEqual(template_helper.money_format(12.64, store), '$13')
        self.assertEqual(template_helper.money_format(1200.00, store), '$1,200')
        self.assertEqual(template_helper.money_format(-1200.00, store), '- $1,200')

    def test_money_format_amount_with_comma_separator(self):
        store = Mock()

        store.currency_format = "${{amount_with_comma_separator}}"
        self.assertEqual(template_helper.money_format(12.34, store), '$12.34')

        store.currency_format = "${{   amount_with_comma_separator    }}"
        self.assertEqual(template_helper.money_format(12.34, store), '$12.34')

    def test_money_format_amount_no_decimals_with_comma_separator(self):
        store = Mock()
        store.currency_format = "${{amount_no_decimals_with_comma_separator}}"

        self.assertEqual(template_helper.money_format(12.34, store), '$12')
        self.assertEqual(template_helper.money_format(12.64, store), '$13')

    def test_force_https_http(self):
        url = 'http://cdn.aliexpress.com/simple.png'
        should_be = '//cdn.aliexpress.com/simple.png'
        self.assertEqual(template_helper.force_https(url), should_be)

    def test_force_https_https(self):
        url = 'https://cdn.aliexpress.com/simple.png'
        should_be = '//cdn.aliexpress.com/simple.png'
        self.assertEqual(template_helper.force_https(url), should_be)

    def test_force_https_no_scheme(self):
        url = '//cdn.aliexpress.com/simple.png'
        should_be = '//cdn.aliexpress.com/simple.png'
        self.assertEqual(template_helper.force_https(url), should_be)

    def test_force_https_no_scheme_error(self):
        # TODO: Add // for url without a scheme? might be problem for relative paths
        url = 'cdn.aliexpress.com/simple.png'
        should_be = 'cdn.aliexpress.com/simple.png'
        self.assertEqual(template_helper.force_https(url), should_be)
