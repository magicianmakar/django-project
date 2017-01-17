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
        self.error_message = "Permission Denied: You don't have permission to perform this action"
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


class AutocompleteTestCase(TestCase):
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

    def test_returns_suggestions(self):
        product = f.ShopifyProductFactory(store=self.store, user=self.user)
        supplier = f.ProductSupplierFactory(store=self.store, product=product, supplier_name='Test')
        r = self.client.get('/autocomplete/supplier-name?store={}&query=tes'.format(self.store.id))
        content = json.loads(r.content)
        suggestion = content['suggestions'].pop()
        self.assertEquals(suggestion['value'], supplier.supplier_name)

    def test_must_not_suggest_names_from_other_users_stores(self):
        store = f.ShopifyStoreFactory()
        product = f.ShopifyProductFactory(store=store, user=store.user)
        f.ProductSupplierFactory(product=product, supplier_name='Test')
        r = self.client.get('/autocomplete/supplier-name?store={}&query=tes'.format(store.id))
        self.assertEquals(r.status_code, 403)


class AffiliateTestCase(TestCase):
    def setUp(self):
        self.user = f.UserFactory(username='test')
        self.password = 'test'
        self.user.set_password(self.password)
        self.user.save()

        self.client.login(username=self.user.username, password=self.password)

        self.place_order_data = {
            'product': 'https://www.aliexpress.com/item/-/32735736988.html',
            'SAPlaceOrder': '1_123_123'
        }

    @patch('random.choice', Mock(return_value='ali'))
    @patch('leadgalaxy.utils.get_aliexpress_affiliate_url')
    def test_user_without_affiliate_aliexpress(self, affiliate_url):
        affiliate_url.return_value = (
            r'http://s.click.aliexpress.com/deep_link.htm?'
            r'aff_short_key=qJIMbIe&dl_target_url=https%3A%2F%2Fwww.aliexpress.com%2F'
            r'item%2F-%2F32735736988.html'
        )

        r = self.client.get('/orders/place', self.place_order_data)

        affiliate_url.assert_called_with(
            '37954', 'shopifiedapp', self.place_order_data['product']
        )

        # Ensure extra query are well encoded
        self.assertIn(r'%3FSAPlaceOrder%3D{}'.format(self.place_order_data['SAPlaceOrder']), r['location'])

    @patch('random.choice')
    @patch('leadgalaxy.utils.get_admitad_affiliate_url')
    @patch('leadgalaxy.utils.get_aliexpress_affiliate_url')
    @patch('leadgalaxy.models.UserProfile.can', Mock(return_value=True))
    def test_user_disable_affiliate(self, get_aliexpress_affiliate_url, get_admitad_affiliate_url, random_choice):
        self.user.set_config('_disable_affiliate', True)

        r = self.client.get('/orders/place', self.place_order_data)

        get_admitad_affiliate_url.assert_not_called()
        get_aliexpress_affiliate_url.assert_not_called()
        random_choice.assert_not_called()

        self.assertIn(r'SAPlaceOrder={}'.format(self.place_order_data['SAPlaceOrder']), r['location'])

    @patch('random.choice', Mock(return_value='admitad'))
    @patch('leadgalaxy.utils.get_admitad_affiliate_url')
    def test_user_without_affiliate_admitad(self, affiliate_url):
        affiliate_url.return_value = (
            r'https://alitems.com/g/1e8d114494c02ea3d6a016525dc3e8/?'
            r'ulp=https%3A%2F%2Fwww.aliexpress.com%2Fitem%2F-%2F32735736988.html'
        )

        r = self.client.get('/orders/place', self.place_order_data)

        affiliate_url.assert_called_with(
            '1e8d114494c02ea3d6a016525dc3e8', self.place_order_data['product']
        )

        # Ensure extra query are well encoded
        self.assertIn(r'%3FSAPlaceOrder%3D{}'.format(self.place_order_data['SAPlaceOrder']), r['location'])

    @patch('random.choice')
    @patch('leadgalaxy.utils.get_aliexpress_affiliate_url')
    @patch('leadgalaxy.models.UserProfile.can', Mock(return_value=True))
    def test_user_with_affiliate_aliexpress(self, affiliate_url, random_choice):
        self.user.set_config('aliexpress_affiliate_key', '12345678')
        self.user.set_config('aliexpress_affiliate_tracking', 'abcdef')

        affiliate_url.return_value = (
            r'http://s.click.aliexpress.com/deep_link.htm?'
            r'aff_short_key=qJIMbIe&dl_target_url=https%3A%2F%2Fwww.aliexpress.com%2F'
            r'item%2F-%2F32735736988.html'
        )

        r = self.client.get('/orders/place', self.place_order_data)

        affiliate_url.assert_called_with(
            self.user.get_config('aliexpress_affiliate_key'),
            self.user.get_config('aliexpress_affiliate_tracking'),
            self.place_order_data['product']
        )

        # Always use Aliexpress
        random_choice.assert_not_called()

    @patch('random.choice')
    @patch('leadgalaxy.utils.get_admitad_affiliate_url')
    @patch('leadgalaxy.models.UserProfile.can', Mock(return_value=True))
    def test_user_with_affiliate_admitad(self, affiliate_url, random_choice):
        self.user.set_config('admitad_site_id', '987654321')

        affiliate_url.return_value = (
            r'https://alitems.com/g/1e8d114494c02ea3d6a016525dc3e8/?'
            r'ulp=https%3A%2F%2Fwww.aliexpress.com%2Fitem%2F-%2F32735736988.html'
        )

        r = self.client.get('/orders/place', self.place_order_data)

        affiliate_url.assert_called_with(
            self.user.get_config('admitad_site_id'),
            self.place_order_data['product']
        )

        # Always use Aliexpress
        random_choice.assert_not_called()

    @patch('random.choice')
    @patch('leadgalaxy.utils.get_admitad_affiliate_url')
    @patch('leadgalaxy.utils.get_aliexpress_affiliate_url')
    @patch('leadgalaxy.models.UserProfile.can', Mock(return_value=True))
    def test_user_with_both_affiliates(self, get_aliexpress_affiliate_url, get_admitad_affiliate_url, random_choice):
        self.user.set_config('aliexpress_affiliate_key', '12345678')
        self.user.set_config('aliexpress_affiliate_tracking', 'abcdef')
        self.user.set_config('admitad_site_id', '987654321')

        get_admitad_affiliate_url.return_value = (
            r'https://alitems.com/g/1e8d114494c02ea3d6a016525dc3e8/?'
            r'ulp=https%3A%2F%2Fwww.aliexpress.com%2Fitem%2F-%2F32735736988.html'
        )

        r = self.client.get('/orders/place', self.place_order_data)

        get_admitad_affiliate_url.assert_called_with(
            self.user.get_config('admitad_site_id'),
            self.place_order_data['product']
        )

        # Use Admitad only when user have both Aliexpress and Admitad
        get_aliexpress_affiliate_url.assert_not_called()
        random_choice.assert_not_called()
