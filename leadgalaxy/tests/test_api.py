import json
import uuid
from datetime import timedelta

from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from mock import patch, Mock

import factories as f
from lib.test import BaseTestCase


class ProductsApiTestCase(BaseTestCase):
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


# Fix for last_seen cache
@override_settings(CACHES={'default': {'BACKEND': 'django.core.cache.backends.dummy.DummyCache'}})
class SyncAliexpressTestCase(BaseTestCase):
    def setUp(self):
        self.password = 'test'
        self.parent_user = f.UserFactory()
        self.parent_user.set_password(self.password)
        self.parent_user.save()

        self.subuser = f.UserFactory()
        self.subuser.profile.subuser_parent = self.parent_user
        self.subuser.profile.save()
        self.subuser.set_password(self.password)
        self.subuser.save()

        permission = f.AppPermissionFactory(name='orders.use')
        self.parent_user.profile.plan.permissions.add(permission)

        self.store = f.ShopifyStoreFactory(user=self.parent_user)
        self.subuser.profile.subuser_stores.add(self.store)

        created_at = timezone.now()
        for i in range(10):
            with patch('django.utils.timezone.now', Mock(return_value=created_at - timedelta(days=3*i))):  # mock auto_now_add=True
                # Unfulfilled
                f.ShopifyOrderTrackFactory(user=self.parent_user,
                                           store=self.store)

                # Fulfilled
                f.ShopifyOrderTrackFactory(user=self.parent_user,
                                           store=self.store,
                                           source_id=uuid.uuid4().hex,
                                           source_tracking='1234567890',
                                           shopify_status='fulfilled',
                                           source_status='FINISH')

    @patch('leadgalaxy.utils.get_tracking_orders')
    def user_login(self, user, get_tracking_orders):
        get_tracking_orders.return_value = []
        logged_in = self.client.login(username=user.username, password=self.password)

        # Access page before API
        self.client.get(reverse('orders_track'))

        return logged_in

    def get_request(self, url, data, response_status=200):
        r = self.client.get(url, data, content_type='application/json')
        self.assertEquals(r.status_code, response_status)

        return r

    def test_orders_access_permission(self):
        data = {'store': self.store.pk}

        self.user_login(self.parent_user)
        response = self.get_request('/api/order-fulfill', data)
        self.assertNotEquals(response.status_code, 402)

        self.client.logout()

        self.user_login(self.subuser)
        response = self.get_request('/api/order-fulfill', data)
        self.assertNotEquals(response.status_code, 402)

    def test_subuser_order_unfulfilled_only_count(self):
        self.user_login(self.subuser)

        data = {
            'store': self.store.pk,
            'all': 'true',
            'unfulfilled_only': 'true',
            'created_at': '',
            'count_only': 'true'
        }

        response = self.get_request('/api/order-fulfill', data)
        json_response = json.loads(response.content)
        self.assertEquals(json_response['pending'], 10)

    def test_order_all_only_count(self):
        self.user_login(self.parent_user)

        data = {
            'store': self.store.pk,
            'all': 'true',
            'unfulfilled_only': 'false',
            'created_at': '',
            'count_only': 'true'
        }

        response = self.get_request('/api/order-fulfill', data)
        json_response = json.loads(response.content)
        self.assertEquals(json_response['pending'], 20)

    def test_last_week_orders_only(self):
        self.user_login(self.parent_user)

        created_at = '{}-{}'.format(
            (timezone.now() - timedelta(days=7)).strftime('%m/%d/%Y'),
            timezone.now().strftime('%m/%d/%Y')
        )

        data = {
            'store': self.store.pk,
            'all': 'false',
            'unfulfilled_only': 'false',
            'created_at': created_at,
            'count_only': 'true',
        }

        response = self.get_request('/api/order-fulfill', data)
        json_response = json.loads(response.content)
        self.assertEquals(json_response['pending'], 6)

    def test_unfulfilled_only(self):
        self.user_login(self.parent_user)

        created_at = '{}-{}'.format(
            (timezone.now() - timedelta(days=7)).strftime('%m/%d/%Y'),
            timezone.now().strftime('%m/%d/%Y')
        )
        data = {
            'store': self.store.pk,
            'all': 'false',
            'unfulfilled_only': 'true',
            'created_at': created_at,
            'count_only': 'false',
        }

        response = self.get_request('/api/order-fulfill', data)
        orders = json.loads(response.content)

        for order in orders:
            self.assertEqual(order['source_id'], '')
