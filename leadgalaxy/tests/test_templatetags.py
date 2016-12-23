from django.test import TestCase

from mock import Mock

from leadgalaxy.templatetags import template_helper


class TagsTestCase(TestCase):
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

    def test_money_format(self):
        store = Mock()
        store.currency_format = "${{amount}}"

        self.assertEqual(template_helper.money_format(0, store), '$0.00')
        self.assertEqual(template_helper.money_format(0.0, store), '$0.00')
        self.assertEqual(template_helper.money_format(12.34, store), '$12.34')
        self.assertEqual(template_helper.money_format(None, store), '$')
        self.assertEqual(template_helper.money_format(None, None), '$')

    def test_money_format_euro(self):
        store = Mock()
        store.currency_format = u"\u20ac {{amount}}"
        self.assertEqual(template_helper.money_format(12.34, store), u'\u20ac 12.34')
