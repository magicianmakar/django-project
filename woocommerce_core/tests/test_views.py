import json

from mock import patch, Mock

from django.test import TestCase
from django.core.urlresolvers import reverse
from django.core.exceptions import PermissionDenied

from leadgalaxy.tests.factories import UserFactory, GroupPlanFactory, AppPermissionFactory

from ..models import WooStore, WooProduct

from .factories import (
    WooStoreFactory,
    WooProductFactory,
)


class StoreListTestCase(TestCase):
    def setUp(self):
        self.user = UserFactory(username='test')
        self.password = 'test'
        self.user.set_password(self.password)
        self.user.save()

        self.user.profile.plan = GroupPlanFactory()
        permission = AppPermissionFactory(name='woocommerce.use')
        self.user.profile.plan.permissions.add(permission)
        self.user.profile.save()

        self.path = reverse('woo:index')

    def login(self):
        self.client.login(username=self.user.username, password=self.password)

    def test_must_be_logged_in(self):
        r = self.client.get(self.path)
        redirect_to = reverse('login') + '?next=' + self.path
        self.assertRedirects(r, redirect_to)

    def test_must_return_ok(self):
        self.login()
        r = self.client.get(self.path)
        self.assertTrue(r.status_code, 200)

    def test_must_return_correct_template(self):
        self.login()
        r = self.client.get(self.path)
        self.assertTemplateUsed(r, 'woocommerce/index.html')

    def test_must_only_list_active_stores(self):
        WooStoreFactory(user=self.user, is_active=True)
        WooStoreFactory(user=self.user, is_active=False)
        self.login()
        r = self.client.get(self.path)
        self.assertEqual(r.context['stores'].count(), 1)

    def test_must_have_breadcrumbs(self):
        self.login()
        r = self.client.get(self.path)
        self.assertEqual(r.context['breadcrumbs'], ['Stores'])


class StoreCreateTestCase(TestCase):
    def setUp(self):
        self.user = UserFactory(username='test')
        self.password = 'test'
        self.user.set_password(self.password)
        self.user.save()

        self.subuser = UserFactory()
        self.subuser_password = 'test'
        self.subuser.set_password(self.subuser_password)
        self.subuser.save()
        self.subuser.profile.subuser_parent = self.user
        self.subuser.profile.save()

        self.data = {
            'title': 'Test Store',
            'api_url': 'https://woostore.com',
            'api_key': 'ck_323fce33402a70913e4cdbbdffa14bdb1cfb9a50',
            'api_password': 'cs_e32287eb90192ab2476015f9a69a30bb015dbdaf'}

        self.headers = {'HTTP_X_REQUESTED_WITH': 'XMLHttpRequest'}
        self.path = '/api/woo/store-add'

    def login(self):
        self.client.login(username=self.user.username, password=self.password)

    @patch('woocommerce_core.api.WooStoreApi.check_store_credentials', Mock(return_value=True))
    @patch('shopified_core.permissions.user_can_add', Mock(return_value=None))
    @patch('shopified_core.permissions.can_add_store', Mock(return_value=(True, 2, 0)))
    def test_must_add_store_to_user(self):
        self.login()
        r = self.client.post(self.path, self.data, **self.headers)

        store = WooStore.objects.first()

        self.assertEqual(store.user, self.user)
        self.assertEqual(r.reason_phrase, 'OK')

    def test_must_not_allow_subusers_to_create(self):
        self.client.login(username=self.subuser.username, password=self.subuser_password)
        r = self.client.post(self.path, self.data, **self.headers)
        self.assertIn(r.status_code, [401, 403])


class StoreReadTestCase(TestCase):
    def setUp(self):
        self.user = UserFactory(username='test')
        self.password = 'test'
        self.user.set_password(self.password)
        self.user.save()

        self.subuser = UserFactory()
        self.subuser_password = 'test'
        self.subuser.set_password(self.subuser_password)
        self.subuser.save()
        self.subuser.profile.subuser_parent = self.user
        self.subuser.profile.save()

        self.headers = {'HTTP_X_REQUESTED_WITH': 'XMLHttpRequest'}
        self.path = '/api/woo/store'

    def login(self):
        self.client.login(username=self.user.username, password=self.password)

    def test_store_id_is_required(self):
        self.login()
        r = self.client.get(self.path, **self.headers)
        self.assertEqual(r.status_code, 400)

    @patch('shopified_core.permissions.user_can_view', Mock(return_value=None))
    def test_user_must_be_able_to_get_own_store(self):
        self.login()
        store = WooStoreFactory(user=self.user)
        r = self.client.get(self.path, {'id': store.id}, **self.headers)
        data = json.loads(r.content)
        self.assertEqual(data['id'], store.id)

    @patch('shopified_core.permissions.user_can_view', Mock(return_value=None))
    def test_user_must_not_be_able_to_get_not_owned_store(self):
        self.login()
        store = WooStoreFactory()
        r = self.client.get(self.path, {'id': store.id}, **self.headers)
        self.assertEqual(r.status_code, 404)

    @patch('shopified_core.permissions.user_can_view', Mock(return_value=None))
    def test_subuser_must_be_able_to_get_models_user_store(self):
        self.client.login(username=self.subuser.username, password=self.subuser_password)
        store = WooStoreFactory(user=self.subuser.models_user)
        r = self.client.get(self.path, {'id': store.id}, **self.headers)
        data = json.loads(r.content)
        self.assertEqual(data['id'], store.id)


class StoreUpdateTestCase(TestCase):
    def setUp(self):
        self.user = UserFactory(username='test')
        self.password = 'test'
        self.user.set_password(self.password)
        self.user.save()

        self.subuser = UserFactory()
        self.subuser_password = 'test'
        self.subuser.set_password(self.subuser_password)
        self.subuser.save()
        self.subuser.profile.subuser_parent = self.user
        self.subuser.profile.save()

        self.data = {
            'title': 'Test Store',
            'api_url': 'https://woostore.com',
            'api_key': 'ck_323fce33402a70913e4cdbbdffa14bdb1cfb9a50',
            'api_password': 'cs_e32287eb90192ab2476015f9a69a30bb015dbdaf'}

        self.store = WooStoreFactory(user=self.user, **self.data)

        self.headers = {'HTTP_X_REQUESTED_WITH': 'XMLHttpRequest'}
        self.path = '/api/woo/store-update'

    def login(self):
        self.client.login(username=self.user.username, password=self.password)

    def test_store_id_is_required(self):
        self.login()
        r = self.client.post(self.path, {'title': 'New Title'}, **self.headers)
        self.assertEqual(r.status_code, 400)

    @patch('woocommerce_core.api.WooStoreApi.check_store_credentials', Mock(return_value=True))
    @patch('shopified_core.permissions.user_can_edit', Mock(return_value=None))
    def test_user_must_be_able_to_update(self):
        self.login()
        data = {
            'id': self.store.id,
            'title': 'New Title',
            'api_url': 'https://newwoostore.com',
            'api_key': 'new key',
            'api_password': 'new password'}

        r = self.client.post(self.path, data, **self.headers)
        self.store.refresh_from_db()

        self.assertEqual(self.store.title, data['title'])
        self.assertEqual(self.store.api_url, data['api_url'])
        self.assertEqual(self.store.api_key, data['api_key'])
        self.assertEqual(self.store.api_password, data['api_password'])
        self.assertEqual(r.reason_phrase, 'OK')

    def test_must_not_allow_subusers_to_update(self):
        self.client.login(username=self.subuser.username, password=self.subuser_password)
        data = {
            'id': self.store.id,
            'title': 'New Title',
            'api_url': 'https://newwoostore.com',
            'api_key': 'new key',
            'api_password': 'new password'}

        r = self.client.post(self.path, data, **self.headers)
        self.assertIn(r.status_code, [401, 403])


class StoreDeleteTestCase(TestCase):
    def setUp(self):
        self.user = UserFactory(username='test')
        self.password = 'test'
        self.user.set_password(self.password)
        self.user.save()

        self.subuser = UserFactory()
        self.subuser_password = 'test'
        self.subuser.set_password(self.subuser_password)
        self.subuser.save()
        self.subuser.profile.subuser_parent = self.user
        self.subuser.profile.save()

        self.store = WooStoreFactory(user=self.user)
        self.headers = {'HTTP_X_REQUESTED_WITH': 'XMLHttpRequest'}
        self.path = '/api/woo/store?id=%s' % self.store.pk

    def test_must_be_logged_in(self):
        r = self.client.delete(self.path, **self.headers)
        self.assertEqual(r.status_code, 401)

    def test_store_id_is_required(self):
        self.client.login(username=self.user.username, password=self.password)
        r = self.client.delete('/api/woo/store', **self.headers)
        self.assertEqual(r.status_code, 400)

    def test_user_must_be_able_to_delete_own_store(self):
        self.client.login(username=self.user.username, password=self.password)
        r = self.client.delete(self.path, **self.headers)
        count = self.user.woostore_set.filter(is_active=True).count()
        self.assertTrue(r.reason_phrase, 'OK')
        self.assertEqual(count, 0)

    def test_must_not_allow_subusers_to_delete(self):
        self.client.login(username=self.subuser.username, password=self.subuser_password)
        r = self.client.delete(self.path, **self.headers)
        self.assertEqual(r.status_code, 403)


class ProductsListTestCase(TestCase):
    def setUp(self):
        self.user = UserFactory(username='test')
        self.password = 'test'
        self.user.set_password(self.password)
        self.user.save()

        self.user.profile.plan = GroupPlanFactory()
        permission = AppPermissionFactory(name='woocommerce.use')
        self.user.profile.plan.permissions.add(permission)
        self.user.profile.save()

        self.path = reverse('woo:products_list')

    def login(self):
        self.client.login(username=self.user.username, password=self.password)

    def test_must_be_logged_in(self):
        r = self.client.get(self.path)
        redirect_to = reverse('login') + '?next=' + self.path
        self.assertRedirects(r, redirect_to)

    def test_must_return_ok(self):
        self.login()
        r = self.client.get(self.path)
        self.assertTrue(r.status_code, 200)

    def test_must_return_correct_template(self):
        self.login()
        r = self.client.get(self.path)
        self.assertTemplateUsed(r, 'woocommerce/products_grid.html')


class ProductSaveTestCase(TestCase):
    def setUp(self):
        self.path = '/api/woo/product-save'

        self.user = UserFactory(username='test')
        self.password = 'test'
        self.user.set_password(self.password)
        self.user.save()

        self.user.profile.plan = GroupPlanFactory()
        self.woocommerce = AppPermissionFactory(name='woocommerce.use')
        self.import_from_any = AppPermissionFactory(name='import_from_any.use')
        self.user.profile.plan.permissions.add(self.woocommerce, self.import_from_any)
        self.user.profile.save()

        self.store = WooStoreFactory(user=self.user)

        self.headers = {
            'HTTP_X_REQUESTED_WITH': 'XMLHttpRequest',
            'content_type': 'application/json',
        }

        self.product_data = {
            'title': 'Test Product',
            'store': {
                'name': 'Test Store',
                'url': 'http://teststore.com',
            },
        }

        self.data = {
            'store': self.store.id,
            'original_url': 'http://test.com',
            'data': json.dumps(self.product_data),
        }

    def login(self):
        self.client.login(username=self.user.username, password=self.password)

    @patch('shopified_core.permissions.user_can_add', Mock(return_value=True))
    @patch('shopified_core.permissions.can_add_product', Mock(return_value=(True, 1, 0)))
    def test_user_can_add_if_logged_in(self):
        self.login()
        r = self.client.post(self.path, json.dumps(self.data), **self.headers)
        data = json.loads(r.content)
        product_id = data['product']['id']
        product = WooProduct.objects.get(pk=product_id)
        self.assertEqual(product.title, self.product_data['title'])

    @patch('shopified_core.permissions.user_can_add', Mock(return_value=True))
    @patch('shopified_core.permissions.can_add_product', Mock(return_value=(True, 1, 0)))
    def test_user_must_be_logged_in(self):
        r = self.client.post(self.path, json.dumps(self.data), **self.headers)
        self.assertEqual(r.status_code, 401)

    @patch('shopified_core.permissions.user_can_add', Mock(return_value=True))
    @patch('shopified_core.permissions.can_add_product', Mock(return_value=(True, 1, 0)))
    def test_first_store_is_used_if_no_store_in_data(self):
        self.login()
        self.data.pop('store')
        r = self.client.post(self.path, json.dumps(self.data), **self.headers)
        data = json.loads(r.content)
        product_id = data['product']['id']
        product = WooProduct.objects.get(pk=product_id)
        store = self.user.profile.get_woo_stores().first()
        self.assertEqual(store.id, product.store.id)

    @patch('shopified_core.permissions.user_can_add', Mock(return_value=True))
    @patch('shopified_core.permissions.can_add_product', Mock(return_value=(True, 1, 0)))
    def test_user_cant_add_to_store_owned_by_others(self):
        self.login()
        self.data['store'] = WooStoreFactory().pk
        r = self.client.post(self.path, json.dumps(self.data), **self.headers)
        self.assertTrue('error' in json.loads(r.content))

    @patch('shopified_core.permissions.user_can_add', Mock(return_value=True))
    @patch('shopified_core.permissions.can_add_product', Mock(return_value=(True, 1, 0)))
    def test_user_cant_add_to_nonexistent_store(self):
        self.login()
        self.data['store'] = 999
        r = self.client.post(self.path, json.dumps(self.data), **self.headers)
        self.assertTrue('error' in json.loads(r.content))

    @patch('shopified_core.permissions.user_can_add', Mock(return_value=True))
    @patch('shopified_core.permissions.can_add_product', Mock(return_value=(True, 1, 0)))
    def test_original_url_must_be_valid(self):
        self.login()
        self.data['original_url'] = 'NotValid'
        r = self.client.post(self.path, json.dumps(self.data), **self.headers)
        self.assertTrue('error' in json.loads(r.content))

    @patch('shopified_core.permissions.user_can_add', Mock(return_value=True))
    @patch('shopified_core.permissions.can_add_product', Mock(return_value=(True, 1, 0)))
    def test_user_must_have_permission(self):
        self.login()
        self.user.profile.plan.permissions.remove(self.import_from_any)
        r = self.client.post(self.path, json.dumps(self.data), **self.headers)
        self.assertTrue('error' in json.loads(r.content))

    @patch('shopified_core.permissions.user_can_add', Mock(return_value=True))
    @patch('shopified_core.permissions.can_add_product', Mock(return_value=(False, 1, 0)))
    def test_user_needs_can_add_product_permission(self):
        self.login()
        r = self.client.post(self.path, json.dumps(self.data), **self.headers)
        self.assertTrue('error' in json.loads(r.content))

    @patch('shopified_core.permissions.user_can_add', Mock(side_effect=PermissionDenied()))
    @patch('shopified_core.permissions.can_add_product', Mock(return_value=(True, 1, 0)))
    def test_user_needs_user_can_add_permission(self):
        self.login()
        r = self.client.post(self.path, json.dumps(self.data), **self.headers)
        self.assertTrue('error' in json.loads(r.content))

    @patch('shopified_core.permissions.user_can_edit', Mock(return_value=True))
    def test_user_can_update_product_title(self):
        self.login()
        product_data = {'title': 'Old Title'}
        product = WooProductFactory(store=self.store, user=self.user, data=json.dumps(product_data))
        new_title = 'New Title'
        self.data['product'] = product.id
        self.data['data'] = json.dumps({'title': new_title})
        self.client.post(self.path, json.dumps(self.data), **self.headers)
        product.refresh_from_db()
        self.assertEqual(product.title, new_title)

    @patch('shopified_core.permissions.user_can_edit', Mock(return_value=True))
    def test_user_can_update_product_price(self):
        self.login()
        product_data = {'price': 1.0}
        product = WooProductFactory(store=self.store, user=self.user, data=json.dumps(product_data))
        new_price = 2.0
        self.data['product'] = product.id
        self.data['data'] = json.dumps({'price': new_price})
        self.client.post(self.path, json.dumps(self.data), **self.headers)
        product.refresh_from_db()
        self.assertEqual(product.price, new_price)
