import json

from django.test import TestCase
from django.contrib.auth.models import User

from mock import patch, Mock

import factories as f

class ProductsApiTestCase(TestCase):
    def setUp(self):
        self.parent_user = f.UserFactory()
        self.user = f.UserFactory()
        self.password = 'test'
        self.user.set_password(self.password)
        self.user.save()

        self.store = f.ShopifyStoreFactory(user=self.user)
        self.client.login(username=self.user.username, password=self.password)

    @patch('shopified_core.mixins.ApiResponseMixin.get_user')
    def test_find_products_by_shopify_ids(self, get_api_user):
        get_api_user.return_value = self.user
        product = f.ShopifyProductFactory(store=self.store, user=self.user, shopify_id=12345678)
        supplier = f.ProductSupplierFactory(store=self.store, product=product, supplier_name='Test')
        data = {'store': self.store.id, 'product': product.shopify_id}

        r = self.client.get('/api/find-products', data, content_type='application/json')
        self.assertEquals(r.status_code, 200)
        json_response = json.loads(r.content)
        self.assertIsNotNone(json_response.get(str(product.shopify_id)))

    @patch('shopified_core.mixins.ApiResponseMixin.get_user')
    def test_find_products_by_aliexpress_ids(self, get_api_user):
        get_api_user.return_value = self.user
        source_id = 123
        product = f.ShopifyProductFactory(store=self.store, user=self.user, shopify_id=12345678)
        supplier = f.ProductSupplierFactory(store=self.store, product=product, supplier_name='Test', product_url='aliexpress.com/{}.html'.format(source_id))
        data = {'store': self.store.id, 'aliexpress': supplier.source_id}

        r = self.client.get('/api/find-products', data)
        self.assertEquals(r.status_code, 200)
        json_response = json.loads(r.content)
        self.assertIsNotNone(json_response.get(str(source_id)))
