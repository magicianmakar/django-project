import json

from django.test import TestCase
from django.core.urlresolvers import reverse
from django.core.cache import cache

from mock import patch, Mock

import factories as f

from stripe_subscription.tests.factories import StripeCustomerFactory
from stripe_subscription.models import StripeCustomer

from leadgalaxy.views import get_product


class ProfileViewTestCase(TestCase):
    def setUp(self):
        self.user = f.UserFactory(username='test')
        self.password = 'test'
        self.user.set_password(self.password)
        self.user.save()
        StripeCustomerFactory(user=self.user)

    @patch.object(StripeCustomer, 'source', None)
    @patch.object(StripeCustomer, 'get_invoices')
    def test_get_invoices_is_not_called_on_initial_load(self, get_invoices):
        self.client.login(username=self.user.username, password=self.password)
        response = self.client.get(reverse('user_profile'))
        self.assertEquals(response.status_code, 200)
        self.assertFalse(get_invoices.called)


class ProfileInvoicesTestCase(TestCase):
    def setUp(self):
        self.user = f.UserFactory(username='test')
        self.password = 'test'
        self.user.set_password(self.password)
        self.user.save()
        StripeCustomerFactory(user=self.user)

    def tearDown(self):
        cache.clear()
        cache.close()

    @patch.object(StripeCustomer, 'get_invoices')
    def test_get_invoices_is_called_once_because_of_caching(self, get_invoices):
        get_invoices.return_value = []
        self.client.login(username=self.user.username, password=self.password)
        kwargs = {'HTTP_X_REQUESTED_WITH': 'XMLHttpRequest'}
        self.client.get(reverse('user_profile_invoices'), **kwargs)
        self.client.get(reverse('user_profile_invoices'), **kwargs)
        self.assertEquals(get_invoices.call_count, 1)


class GetProductTestCase(TestCase):
    def setUp(self):
        self.user = f.UserFactory(username='test')
        self.password = 'test'
        self.user.set_password(self.password)
        self.user.profile.delete()
        self.user.save()

        self.store = f.ShopifyStoreFactory()
        self.store.user = self.user
        self.store.save()

        f.UserProfileFactory(user=self.user)

        self.client.login(username=self.user.username, password=self.password)

    def test_products_can_be_filtered_by_title(self):
        product = f.ShopifyProductFactory(
            user=self.user,
            store=self.store,
            data=json.dumps({'title': 'this is a test'})
        )
        f.ShopifyProductFactory(
            user=self.user,
            store=self.store,
            data=json.dumps({'title': 'not retrieved'})
        )
        request = Mock()
        request.user = self.user
        request.GET = {'title': 'test'}

        items = get_product(request, filter_products=True)[0]
        products = [item['qelem'] for item in items]

        self.assertIn(product, products)
        self.assertEquals(len(products), 1)

    def test_products_can_be_sorted_by_title(self):
        product1 = f.ShopifyProductFactory(
            user=self.user,
            store=self.store,
            data=json.dumps({'title': 'this is a test A'})
        )
        product3 = f.ShopifyProductFactory(
            user=self.user,
            store=self.store,
            data=json.dumps({'title': 'this is a test C'})
        )
        product2 = f.ShopifyProductFactory(
            user=self.user,
            store=self.store,
            data=json.dumps({'title': 'this is a test B'})
        )
        request = Mock()
        request.user = self.user
        request.GET = {}

        items = get_product(request, False, sort='-title')[0]
        products = [item['qelem'] for item in items]

        self.assertEquals([product3, product2, product1], products)

    def test_products_can_be_sorted_by_price(self):
        product1 = f.ShopifyProductFactory(user=self.user, store=self.store, data=json.dumps({'price': 1.0}))
        product3 = f.ShopifyProductFactory(user=self.user, store=self.store, data=json.dumps({'price': 3.0}))
        product2 = f.ShopifyProductFactory(user=self.user, store=self.store, data=json.dumps({'price': 2.0}))
        request = Mock()
        request.user = self.user
        request.GET = {}

        items = get_product(request, False, sort='-price')[0]
        products = [item['qelem'] for item in items]

        self.assertEquals(
            map(lambda p: float(p.price), [product3, product2, product1]),
            map(lambda p: float(p.price), products)
        )


class SubuserpermissionsApiTestCase(TestCase):
    def setUp(self):
        self.error_message = "You don't have permission to perform this action."
        self.parent_user = f.UserFactory()
        self.user = f.UserFactory()
        self.user.profile.subuser_parent = self.parent_user
        self.user.profile.save()
        self.password = 'test'
        self.user.set_password(self.password)
        self.user.save()
        self.store = f.ShopifyStoreFactory(user=self.parent_user)
        self.client.login(username=self.user.username, password=self.password)

    @patch('leadgalaxy.tasks.export_product', Mock(return_value=None))
    @patch('leadgalaxy.utils.fix_product_url', Mock(return_value={}))
    @patch('leadgalaxy.utils.get_api_user')
    def test_subuser_can_save_for_later_with_permission(self, get_api_user):
        get_api_user.return_value = self.user
        data = json.dumps({'b': False, 'store': self.store.id})
        self.user.profile.subuser_stores.add(self.store)
        r = self.client.post('/api/save-for-later', data, content_type='application/json')
        self.assertEquals(r.status_code, 200)

    @patch('leadgalaxy.tasks.export_product', Mock(return_value=None))
    @patch('leadgalaxy.utils.get_api_user')
    def test_subuser_cant_save_for_later_without_permission(self, get_api_user):
        get_api_user.return_value = self.user
        self.user.profile.subuser_stores.add(self.store)
        permission = self.user.profile.subuser_permissions.get(codename='save_for_later')
        self.user.profile.subuser_permissions.remove(permission)
        data = json.dumps({'b': False, 'store': self.store.id})
        r = self.client.post('/api/save-for-later', data, content_type='application/json')
        self.assertEquals(r.status_code, 403)

    @patch('leadgalaxy.tasks.export_product', Mock(return_value=None))
    @patch('leadgalaxy.utils.fix_product_url', Mock(return_value={}))
    @patch('leadgalaxy.utils.get_api_user')
    def test_subuser_can_send_to_shopify_with_permission(self, get_api_user):
        get_api_user.return_value = self.user
        data = json.dumps({'b': False, 'store': self.store.id})
        self.user.profile.subuser_stores.add(self.store)
        r = self.client.post('/api/shopify', data, content_type='application/json')
        self.assertEquals(r.status_code, 200)

    @patch('leadgalaxy.tasks.export_product', Mock(return_value=None))
    @patch('leadgalaxy.utils.get_api_user')
    def test_subuser_cant_send_to_shopify_without_permission(self, get_api_user):
        get_api_user.return_value = self.user
        self.user.profile.subuser_stores.add(self.store)
        permission = self.user.profile.subuser_permissions.get(codename='send_to_shopify')
        self.user.profile.subuser_permissions.remove(permission)
        data = json.dumps({'b': False, 'store': self.store.id})
        r = self.client.post('/api/shopify', data, content_type='application/json')
        self.assertEquals(r.status_code, 403)

    @patch('leadgalaxy.tasks.export_product', Mock(return_value=None))
    @patch('leadgalaxy.utils.fix_product_url', Mock(return_value={}))
    @patch('leadgalaxy.utils.get_api_user')
    def test_subuser_can_update_shopify_with_permission(self, get_api_user):
        get_api_user.return_value = self.user
        data = json.dumps({'b': False, 'store': self.store.id})
        self.user.profile.subuser_stores.add(self.store)
        r = self.client.post('/api/shopify-update', data, content_type='application/json')
        self.assertEquals(r.status_code, 200)

    @patch('leadgalaxy.tasks.export_product', Mock(return_value=None))
    @patch('leadgalaxy.utils.get_api_user')
    def test_subuser_cant_update_shopify_without_permission(self, get_api_user):
        get_api_user.return_value = self.user
        self.user.profile.subuser_stores.add(self.store)
        permission = self.user.profile.subuser_permissions.get(codename='send_to_shopify')
        self.user.profile.subuser_permissions.remove(permission)
        data = json.dumps({'b': False, 'store': self.store.id})
        r = self.client.post('/api/shopify-update', data, content_type='application/json')
        self.assertEquals(r.status_code, 403)

    def test_subuser_can_delete_product_with_permission(self):
        product = f.ShopifyProductFactory(store=self.store, user=self.parent_user)
        self.user.profile.subuser_stores.add(self.store)
        data = {'product': product.id}
        r = self.client.post('/api/product-delete', data)
        self.assertEquals(r.status_code, 200)

    def test_subuser_cant_delete_product_without_permission(self):
        self.user.profile.subuser_stores.add(self.store)
        permission = self.user.profile.subuser_permissions.get(codename='delete_products')
        self.user.profile.subuser_permissions.remove(permission)
        product = f.ShopifyProductFactory(store=self.store, user=self.parent_user)
        data = {'product': product.id}
        r = self.client.post('/api/product-delete', data)
        self.assertEquals(r.status_code, 403)
        json_response = json.loads(r.content)
        self.assertEquals(json_response['error'], self.error_message)

    @patch('leadgalaxy.models.ShopifyStore.pusher_trigger', Mock(return_value=None))
    @patch('leadgalaxy.tasks.mark_as_ordered_note')
    def test_subuser_can_order_fulfill_with_permission(self, mark_as_ordered_note):
        mark_as_ordered_note.delay = Mock(return_value=None)
        self.user.profile.subuser_stores.add(self.store)
        data = {'store': self.store.id, 'order_id': '1', 'line_id': '1', 'aliexpress_order_id': '01234566789'}
        r = self.client.post('/api/order-fulfill', data)
        self.assertEquals(r.status_code, 200)

    def test_subuser_cant_order_fulfill_without_permission(self):
        self.user.profile.subuser_stores.add(self.store)
        permission = self.user.profile.subuser_permissions.get(codename='place_orders')
        self.user.profile.subuser_permissions.remove(permission)
        data = {'store': self.store.id, 'order_id': '1', 'line_id': '1', 'aliexpress_order_id': '01234566789'}
        r = self.client.post('/api/order-fulfill', data)
        self.assertEquals(r.status_code, 403)

    @patch('leadgalaxy.views.utils.order_track_fulfillment', Mock(return_value=None))
    @patch('leadgalaxy.models.ShopifyStore.get_link', Mock(return_value=None))
    @patch('leadgalaxy.views.requests.post')
    def test_subuser_can_fulfill_order_without_permission(self, request_post):
        response = Mock()
        response.json = Mock(return_value={'fulfillment': '1'})
        request_post.return_value = response
        self.user.profile.subuser_stores.add(self.store)
        data = {'fulfill-store': self.store.id, 'fulfill-line-id': 1}
        r = self.client.post('/api/fulfill-order', data)
        self.assertEquals(r.status_code, 200)

    def test_subuser_cant_fulfill_order_without_permission(self):
        self.user.profile.subuser_stores.add(self.store)
        permission = self.user.profile.subuser_permissions.get(codename='place_orders')
        self.user.profile.subuser_permissions.remove(permission)
        data = {'fulfill-store': self.store.id}
        r = self.client.post('/api/fulfill-order', data)
        self.assertEquals(r.status_code, 403)
