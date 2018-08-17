from django.test import TransactionTestCase
from leadgalaxy.models import User, ShopifyStore

MYSHOPIFY_DOMAIN = 'shopified-app-ci.myshopify.com'
PRIVATE_APP_URL = '6bace8a67988e75c29279ac08f7b31bc:41973440f95ee4529b8c739df75aa1f6@%s' % MYSHOPIFY_DOMAIN
SHOPIFY_APP_URL = ':88937df17024aa5126203507e2147f47@%s' % MYSHOPIFY_DOMAIN


class StoreTestCase(TransactionTestCase):
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

    def test_store_api_urls(self):

        for i in ['test1', 'test2', 'test3']:
            store = ShopifyStore.objects.get(title=i)
            self.assertEqual(store.get_link(), "https://%s" % MYSHOPIFY_DOMAIN)
            self.assertEqual(store.get_link('/product/123'), "https://%s/product/123" % MYSHOPIFY_DOMAIN)
            self.assertEqual(store.get_link('product/123'), "https://%s/product/123" % MYSHOPIFY_DOMAIN)

            if store.version == 2:
                self.assertEqual(store.get_link(api=True), "https://%s" % SHOPIFY_APP_URL)
                self.assertEqual(store.get_link('/admin/products.json', api=True), "https://%s/admin/products.json" % SHOPIFY_APP_URL)
                self.assertEqual(store.get_link('admin/products.json', api=True), "https://%s/admin/products.json" % SHOPIFY_APP_URL)
            else:
                self.assertEqual(store.get_link(api=True), "https://%s" % PRIVATE_APP_URL)
                self.assertEqual(store.get_link('/admin/products.json', api=True), "https://%s/admin/products.json" % PRIVATE_APP_URL)
                self.assertEqual(store.get_link('admin/products.json', api=True), "https://%s/admin/products.json" % PRIVATE_APP_URL)

            self.assertEqual(store.get_api_url(hide_keys=True), "https://*:*@%s" % MYSHOPIFY_DOMAIN)

            self.assertEqual(store.get_info['name'], "Shopified App CI")
