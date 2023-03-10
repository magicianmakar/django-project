from django.test import tag
from lib.test import BaseTestCase
from leadgalaxy.models import SHOPIFY_API_VERSION, User, ShopifyStore

MYSHOPIFY_DOMAIN = 'shopified-app-ci.myshopify.com'
PRIVATE_APP_URL = '6bace8a67988e75c29279ac08f7b31bc:41973440f95ee4529b8c739df75aa1f6@%s' % MYSHOPIFY_DOMAIN
SHOPIFY_APP_URL = ':88937df17024aa5126203507e2147f47@%s' % MYSHOPIFY_DOMAIN


class StoreTestCase(BaseTestCase):
    def setUp(self):
        user = User.objects.create(username='me', email='me@localhost.com')
        ShopifyStore.objects.create(user=user,
                                    title="test1",
                                    api_url="https://%s" % PRIVATE_APP_URL)

        ShopifyStore.objects.create(user=user,
                                    title="test2",
                                    api_url="%s" % PRIVATE_APP_URL)

        ShopifyStore.objects.create(user=user,
                                    title="test3",
                                    api_url=SHOPIFY_APP_URL,
                                    version=2,
                                    shop=MYSHOPIFY_DOMAIN)

    @tag('slow')
    def test_store_api_urls(self):

        for i in ['test1', 'test2', 'test3']:
            store = ShopifyStore.objects.get(title=i)
            self.assertEqual(store.get_link(), "https://%s" % MYSHOPIFY_DOMAIN)
            self.assertEqual(store.get_link('/product/123'), "https://%s/product/123" % MYSHOPIFY_DOMAIN)
            self.assertEqual(store.get_link('product/123'), "https://%s/product/123" % MYSHOPIFY_DOMAIN)

            query_params = '?limit=50&page_info=eyJsYXN0X2lkIjo5ODcwMjA1ODM2LCJsYXN0X3ZhbHVlIjoiSCBJUCBDYW1lcmEgMS4wTVAgUGFuJlRpbHQgUDJQIFdpZmkg' \
                           'V2lyZWxlc3MgU2VjdXJpdHkgQ2FtZXJhIHdpdGggTmlnaHQgVmlzaW9uIE1pY3JvIFNEIENhcmQgc2xvdCBPTlZJRiIsImRpcmVjdGlvbiI6Im5leHQifQ'

            if store.version == 2:
                with self.assertRaises(NotImplementedError):
                    self.assertEqual(store.get_link(api=True), "https://%s" % SHOPIFY_APP_URL)

                with self.assertRaises(NotImplementedError):
                    self.assertEqual(store.get_link('/admin/products.json', api=True), f"https://{SHOPIFY_APP_URL}/admin/api/{SHOPIFY_API_VERSION}/products.json")  # noqa

                with self.assertRaises(NotImplementedError):
                    self.assertEqual(store.get_link('admin/products.json', api=True), f"https://{SHOPIFY_APP_URL}/admin/api/{SHOPIFY_API_VERSION}/products.json")  # noqa

                self.assertEqual(store.api('products'), f"https://{SHOPIFY_APP_URL}/admin/api/{SHOPIFY_API_VERSION}/products.json")  # noqa
                self.assertEqual(store.api('products.json'), f"https://{SHOPIFY_APP_URL}/admin/api/{SHOPIFY_API_VERSION}/products.json")  # noqa
                self.assertEqual(store.api('/admin/products.json'), f"https://{SHOPIFY_APP_URL}/admin/api/{SHOPIFY_API_VERSION}/products.json")  # noqa
                self.assertEqual(store.api('admin/products.json'), f"https://{SHOPIFY_APP_URL}/admin/api/{SHOPIFY_API_VERSION}/products.json")  # noqa
                self.assertEqual(store.api('products', 1236), f"https://{SHOPIFY_APP_URL}/admin/api/{SHOPIFY_API_VERSION}/products/1236.json")  # noqa
                self.assertEqual(store.api('products', 1236, 'variants.json'), f"https://{SHOPIFY_APP_URL}/admin/api/{SHOPIFY_API_VERSION}/products/1236/variants.json")  # noqa
                self.assertEqual(store.api('products', 1236, 'variants'), f"https://{SHOPIFY_APP_URL}/admin/api/{SHOPIFY_API_VERSION}/products/1236/variants.json")  # noqa
                self.assertEqual(store.api('products/1236/variants'), f"https://{SHOPIFY_APP_URL}/admin/api/{SHOPIFY_API_VERSION}/products/1236/variants.json")  # noqa
                self.assertEqual(store.api('products/1236/variants.json'), f"https://{SHOPIFY_APP_URL}/admin/api/{SHOPIFY_API_VERSION}/products/1236/variants.json")  # noqa
                self.assertEqual(store.api('products', 1236, 'variants', version='9999-99'), f"https://{SHOPIFY_APP_URL}/admin/api/9999-99/products/1236/variants.json")  # noqa
                self.assertEqual(store.api(f'https://{MYSHOPIFY_DOMAIN}/admin/api/{SHOPIFY_API_VERSION}/products.json'), f"https://{SHOPIFY_APP_URL}/admin/api/{SHOPIFY_API_VERSION}/products.json")  # noqa
                self.assertEqual(store.api(f'https://{MYSHOPIFY_DOMAIN}/admin/api/{SHOPIFY_API_VERSION}/products.json{query_params}'), f"https://{SHOPIFY_APP_URL}/admin/api/{SHOPIFY_API_VERSION}/products.json{query_params}")  # noqa
            else:
                with self.assertRaises(NotImplementedError):
                    self.assertEqual(store.get_link(api=True), "https://%s" % PRIVATE_APP_URL)

                with self.assertRaises(NotImplementedError):
                    self.assertEqual(store.get_link('/admin/products.json', api=True), f"https://{PRIVATE_APP_URL}/admin/api/{SHOPIFY_API_VERSION}/products.json")  # noqa

                with self.assertRaises(NotImplementedError):
                    self.assertEqual(store.get_link('admin/products.json', api=True), f"https://{PRIVATE_APP_URL}/admin/api/{SHOPIFY_API_VERSION}/products.json")  # noqa

                self.assertEqual(store.api('products'), f"https://{PRIVATE_APP_URL}/admin/api/{SHOPIFY_API_VERSION}/products.json")  # noqa
                self.assertEqual(store.api('products.json'), f"https://{PRIVATE_APP_URL}/admin/api/{SHOPIFY_API_VERSION}/products.json")  # noqa
                self.assertEqual(store.api('/admin/products.json'), f"https://{PRIVATE_APP_URL}/admin/api/{SHOPIFY_API_VERSION}/products.json")  # noqa
                self.assertEqual(store.api('admin/products.json'), f"https://{PRIVATE_APP_URL}/admin/api/{SHOPIFY_API_VERSION}/products.json")  # noqa
                self.assertEqual(store.api('products', 1236), f"https://{PRIVATE_APP_URL}/admin/api/{SHOPIFY_API_VERSION}/products/1236.json")  # noqa
                self.assertEqual(store.api('products', 1236, 'variants.json'), f"https://{PRIVATE_APP_URL}/admin/api/{SHOPIFY_API_VERSION}/products/1236/variants.json")  # noqa
                self.assertEqual(store.api('products', 1236, 'variants'), f"https://{PRIVATE_APP_URL}/admin/api/{SHOPIFY_API_VERSION}/products/1236/variants.json")  # noqa
                self.assertEqual(store.api('products/1236/variants'), f"https://{PRIVATE_APP_URL}/admin/api/{SHOPIFY_API_VERSION}/products/1236/variants.json")  # noqa
                self.assertEqual(store.api('products/1236/variants.json'), f"https://{PRIVATE_APP_URL}/admin/api/{SHOPIFY_API_VERSION}/products/1236/variants.json")  # noqa
                self.assertEqual(store.api('products', 1236, 'variants', version='9999-99'), f"https://{PRIVATE_APP_URL}/admin/api/9999-99/products/1236/variants.json")  # noqa
                self.assertEqual(store.api(f'https://{MYSHOPIFY_DOMAIN}/admin/api/{SHOPIFY_API_VERSION}/products.json'), f"https://{PRIVATE_APP_URL}/admin/api/{SHOPIFY_API_VERSION}/products.json")  # noqa
                self.assertEqual(store.api(f'https://{MYSHOPIFY_DOMAIN}/admin/api/{SHOPIFY_API_VERSION}/products.json{query_params}'), f"https://{PRIVATE_APP_URL}/admin/api/{SHOPIFY_API_VERSION}/products.json{query_params}")  # noqa

            self.assertEqual(store.get_api_url(hide_keys=True), "https://*:*@%s" % MYSHOPIFY_DOMAIN)

            self.assertEqual(store.get_info['name'], "Shopified App CI")
