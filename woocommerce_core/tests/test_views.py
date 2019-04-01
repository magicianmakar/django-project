import json
from unittest.mock import patch, Mock

import arrow
from munch import Munch

from lib.test import BaseTestCase
from django.urls import reverse
from django.core.exceptions import PermissionDenied
from django.core.cache import caches

from shopified_core.utils import order_data_cache
from leadgalaxy.tests.factories import (
    UserFactory,
    GroupPlanFactory,
    AppPermissionFactory
)

from .factories import (
    WooBoardFactory,
    WooOrderTrackFactory,
    WooProductFactory,
    WooStoreFactory,
    WooSupplierFactory,
)
from ..models import WooStore, WooProduct


class StoreListTestCase(BaseTestCase):
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


class StoreCreateTestCase(BaseTestCase):
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


class StoreReadTestCase(BaseTestCase):
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


class StoreUpdateTestCase(BaseTestCase):
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


class StoreDeleteTestCase(BaseTestCase):
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


class ProductsListTestCase(BaseTestCase):
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


class ProductSaveTestCase(BaseTestCase):
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


class CallbackEndpointTestCase(BaseTestCase):
    def setUp(self):
        self.user = UserFactory()
        self.store = WooStoreFactory(user=self.user, api_key='', api_password='')
        self.data = {'consumer_key': 'test', 'consumer_secret': '1234', 'user_id': self.user.id}
        self.json_string = json.dumps(self.data)
        self.path = reverse('woo:callback_endpoint', kwargs={'store_hash': self.store.store_hash})

    def test_anonymous_user_can_post_credentials(self):
        r = self.client.post(self.path, data=self.json_string, content_type='application/json')
        self.assertTrue(r.status_code, 200)

    def test_anonymous_user_can_add_store_credentials(self):
        self.client.post(self.path, data=self.json_string, content_type='application/json')
        self.store.refresh_from_db()
        self.assertEqual(self.store.api_key, self.data['consumer_key'])
        self.assertEqual(self.store.api_password, self.data['consumer_secret'])


class ApiTestCase(BaseTestCase):
    def setUp(self):
        self.parent_user = UserFactory()
        self.user = UserFactory()
        self.password = 'test'
        self.user.set_password(self.password)
        self.user.save()

        self.store = WooStoreFactory(user=self.user)
        self.client.login(username=self.user.username, password=self.password)

    @patch('woocommerce_core.models.WooProduct.retrieve')
    def test_post_product_connect(self, product_retrieve):
        product = WooProductFactory(
            store=self.store, user=self.user, source_id=12345678,
            data='''{
            "id": "12345467890",
            "name": "100% Real capacity USB Flash Drive",
            "type": "",
            "tags": [],
            "images": [],
            "textareas": [{"name": "Description", "text": "Ok"}],
            "is_multi": false,
            "regular_price": 10.00,
            "compare_price": 10.00,
            "shipping_weight": "",
            "status": "publish",
            "store": {
                "name": "Suplier 1",
                "url": "https://www.aliexpress.com/item//12345467890.html"
            }}''')

        def retrieve():
            return product.parsed

        product_retrieve.side_effect = retrieve

        data = {'product': product.id, 'store': self.store.id, 'woocommerce': 12345670001}
        r = self.client.post('/api/woo/product-connect', data)
        self.assertEqual(r.status_code, 200)
        product_retrieve.assert_called_once()

        product.refresh_from_db()
        self.assertEqual(product.source_id, data['woocommerce'])

    @patch('woocommerce_core.utils.duplicate_product')
    def test_post_product_duplicate(self, duplicate_product):
        duplicate_product_id = 1111222
        duplicate_product.return_value = Munch({'id': duplicate_product_id})
        product = WooProductFactory(
            store=self.store, user=self.user, source_id=12345678,
            data='''{"store": {
                "name": "Suplier 1",
                "url": "https://www.aliexpress.com/item//12345467890.html"
            }}''')

        data = {'product': product.id}
        r = self.client.post('/api/woo/product-duplicate', data)
        self.assertEqual(r.status_code, 200)

        self.assertEqual(r.json()['product']['id'], duplicate_product_id)
        self.assertEqual(r.json()['product']['url'], f'/woo/product/{duplicate_product_id}')

        duplicate_product.assert_called_with(product)

    @patch('woocommerce_core.utils.get_latest_order_note', Mock(return_value=''))
    @patch('woocommerce_core.utils.add_woo_order_note')
    def test_post_order_note(self, add_woo_order_note):
        order_id = '123456789'
        note = 'Test Note'
        data = {'store': self.store.id, 'order_id': order_id, 'note': note}

        r = self.client.post('/api/woo/order-note', data)
        self.assertEqual(r.status_code, 200)

        add_woo_order_note.assert_called_with(self.store, order_id, note)

    @patch('woocommerce_core.tasks.create_image_zip.delay')
    def test_get_product_image_download(self, create_image_zip):
        product = WooProductFactory(
            store=self.store, user=self.user, source_id=12345678,
            data='''{"store": {
                "name": "Suplier 1",
                "url": "https://www.aliexpress.com/item//12345467890.html"
            }}''')

        data = {'product': product.id}

        r = self.client.get('/api/woo/product-image-download', data)
        self.assertEqual(r.status_code, 422)
        self.assertIn(r.json()['error'], 'Product doesn\'t have any images')

        create_image_zip.assert_not_called()

        images = ["http://www.aliexpress.com/image/1.png"]
        product = WooProductFactory(
            store=self.store, user=self.user, source_id=12345678,
            data=json.dumps({"images": images}))

        data = {'product': product.id}
        r = self.client.get('/api/woo/product-image-download', data)
        self.assertEqual(r.status_code, 200)

        create_image_zip.assert_called_with(images, product.id)

    def test_get_order_data(self):
        store_id, order_id, line_id = self.store.id, 1233, 55466677
        order_key = f'{store_id}_{order_id}_{line_id}'

        data = {
            "id": order_key,
            "quantity": 1,
            "shipping_address": {
                "first_name": "Red",
                "address1": "5541 Great Road ",
                "phone": "922481541",
                "city": "Moody",
                "zip": "35004",
                "province": "Alabama",
                "country": "United States",
                "last_name": "Smin",
                "address2": "",
                "company": "",
                "name": "Red Smin",
                "country_code": "US",
                "province_code": "AL"
            },
            "order_id": order_id,
            "line_id": line_id,
            "product_id": 686,
            "source_id": 32846904328,
            "supplier_id": 1405349,
            "supplier_type": "aliexpress",
            "total": 26.98,
            "store": store_id,
            "order": {"phone": "922481541", "note": "Do not put invoice.", "epacket": True, "auto_mark": True, "phoneCountry": "+1"},
            "products": [],
            "is_bundle": False,
            "variant": [{"sku": "sku-1-193", "title": "black"}, {"sku": "sku-2-201336106", "title": "United States"}],
            "ordered": False,
            "fast_checkout": True,
            "solve": False
        }

        caches['orders'].set(f'woo_order_{order_key}', data)
        self.assertIsNotNone(caches['orders'].get(f'woo_order_{order_key}'))
        self.assertIsNotNone(order_data_cache(f'woo_order_{order_key}'))
        self.assertIsNotNone(order_data_cache(f'{order_key}', prefix='woo_order_'))
        self.assertIsNotNone(order_data_cache(self.store.id, order_id, line_id, prefix='woo_order_'))

        # Store not found
        r = self.client.get('/api/woo/order-data', {'order': f'444{order_key}'})
        self.assertEqual(r.status_code, 404)
        self.assertIn('Store not found', r.content.decode())

        # Order not found
        r = self.client.get('/api/woo/order-data', {'order': f'{order_key}5455'})
        self.assertEqual(r.status_code, 404)
        self.assertIn('Not found:', r.content.decode())

        # Key order prefix is present
        r = self.client.get('/api/woo/order-data', {'order': f'woo_order_{order_key}'})
        self.assertEqual(r.status_code, 200)
        api_data = r.json()
        if api_data.get('status'):
            data['status'] = api_data['status']

        self.assertEqual(json.dumps(api_data, indent=2), json.dumps(data, indent=2))

        # Key prefix removed (default)
        r = self.client.get('/api/woo/order-data', {'order': f'{order_key}'})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), data)
        self.assertFalse(r.json()['ordered'])

        # Test aliexpress_country_code_map
        data['shipping_address']['country_code'] = 'GB'
        caches['orders'].set(f'woo_order_{order_key}', data)

        r = self.client.get('/api/woo/order-data', {'order': f'{order_key}'})
        self.assertEqual(r.status_code, 200)
        self.assertNotEqual(r.json()['shipping_address']['country_code'], data['shipping_address']['country_code'])
        self.assertEqual(r.json()['shipping_address']['country_code'], 'UK')

        # Order Track exist
        WooOrderTrackFactory(user=self.user, store=self.store, order_id=order_id, line_id=line_id, product_id=123)

        r = self.client.get('/api/woo/order-data', {'order': f'{order_key}'})
        ordered = r.json()['ordered']
        self.assertEqual(r.status_code, 200)
        self.assertEqual(type(ordered), dict)
        self.assertIn('time', ordered)
        self.assertIn('link', ordered)

    def test_post_variants_mapping(self):
        product = WooProductFactory(
            store=self.store, user=self.user, source_id=12345678,
            data='''{"store": {
                "name": "Suplier 1",
                "url": "https://www.aliexpress.com/item//12345467890.html"
            }}''')

        supplier = WooSupplierFactory(product=product)

        product.default_supplier = supplier
        product.save()

        var_id = '18395643215934'
        data = {
            'product': product.id,
            'supplier': supplier.id,
            var_id: '[{"title":"China","sku":"sku-1-201336100"}]',
        }

        r = self.client.post('/api/woo/variants-mapping', data)
        self.assertEqual(r.status_code, 200)

        product.refresh_from_db()
        supplier.refresh_from_db()

        self.assertEqual(product.get_variant_mapping(var_id), json.loads(data[var_id]))
        self.assertEqual(product.get_variant_mapping(var_id, for_extension=True), json.loads(data[var_id]))

    def test_post_suppliers_mapping(self):
        product = WooProductFactory(
            store=self.store, user=self.user, source_id=12345678,
            data='''{"store": {
                "name": "Suplier 1",
                "url": "https://www.aliexpress.com/item//12345467890.html"
            }}''')

        supplier1 = WooSupplierFactory(product=product)
        supplier2 = WooSupplierFactory(product=product)

        product.set_default_supplier(supplier1)

        var_ids = ['18401388822590', '18401388888126', '18401388855358']
        data = {
            f'config': 'default',
            f'product': product.id,
            f'shipping_{supplier1.id}_{var_ids[0]}': '[{"country":"FR","method":"FEDEX_IE","country_name":"France","method_name":"Fedex IE ($51.38)"},{"country":"US","method":"EMS","country_name":"United States","method_name":"EMS ($32.14)"}]', # noqa
            f'shipping_{supplier1.id}_{var_ids[1]}': '[{"country":"CA","method":"EMS","country_name":"Canada","method_name":"EMS ($37.49)"}]', # noqa
            f'shipping_{supplier1.id}_{var_ids[2]}': '[{"country_name":"United States","country":"US","method_name":"Fedex IE ($40.53)","method":"FEDEX_IE"}]', # noqa
            f'{var_ids[0]}': '{"supplier":' f'{supplier1.id}' ',"shipping":[{"country":"FR","method":"FEDEX_IE","country_name":"France","method_name":"Fedex IE ($51.38)"},{"country":"US","method":"EMS","country_name":"United States","method_name":"EMS ($32.14)"}]}', # noqa
            f'{var_ids[1]}': '{"supplier":' f'{supplier1.id}' ',"shipping":[{"country":"CA","method":"EMS","country_name":"Canada","method_name":"EMS ($37.49)"}]}', # noqa
            f'{var_ids[2]}': '{"supplier":' f'{supplier1.id}' ',"shipping":[{"country_name":"United States","country":"US","method_name":"Fedex IE ($40.53)","method":"FEDEX_IE"}]}', # noqa
            f'variant_{supplier1.id}_{var_ids[0]}': '[{"sku":"sku-1-173","title":"blue"},{"sku":"sku-2-201336106","title":"United States"}]',
            f'variant_{supplier1.id}_{var_ids[1]}': '[{"sku":"sku-1-366","title":"yellow"},{"sku":"sku-2-201336106","title":"United States"}]',
            f'variant_{supplier1.id}_{var_ids[2]}': '[{"sku":"sku-1-193","title":"black"},{"sku":"sku-2-201336106","title":"United States"}]',
            f'variant_{supplier2.id}_{var_ids[0]}': '[{"sku":"sku-1-201336100","title":"China"},{"sku":"sku-2-193","title":"black"},{"sku":"sku-3-100006192","title":"2"},{"sku":"sku-4-203221828","title":"Player Sets"}]', # noqa
            f'variant_{supplier2.id}_{var_ids[1]}': '[{"sku":"sku-1-201336100","title":"China"},{"sku":"sku-2-193","title":"black"},{"sku":"sku-3-100006192","title":"2"},{"sku":"sku-4-203221828","title":"Player Sets"}]', # noqa
            f'variant_{supplier2.id}_{var_ids[2]}': '[{"sku":"sku-1-201336100","title":"China"},{"sku":"sku-2-193","title":"black"},{"sku":"sku-3-100006192","title":"2"},{"sku":"sku-4-203221828","title":"Player Sets"}]', # noqa
        }

        r = self.client.post('/api/woo/suppliers-mapping', data)
        self.assertEqual(r.status_code, 200)

        product.refresh_from_db()
        supplier1.refresh_from_db()
        supplier2.refresh_from_db()

        self.assertEqual(product.get_variant_mapping(var_ids[0], supplier=supplier1), json.loads(data[f'variant_{supplier1.id}_{var_ids[0]}']))
        self.assertEqual(product.get_variant_mapping(var_ids[1], supplier=supplier1), json.loads(data[f'variant_{supplier1.id}_{var_ids[1]}']))
        self.assertEqual(product.get_variant_mapping(var_ids[2], supplier=supplier1), json.loads(data[f'variant_{supplier1.id}_{var_ids[2]}']))

        self.assertEqual(product.get_variant_mapping(var_ids[0], supplier=supplier2), json.loads(data[f'variant_{supplier2.id}_{var_ids[0]}']))
        self.assertEqual(product.get_variant_mapping(var_ids[1], supplier=supplier2), json.loads(data[f'variant_{supplier2.id}_{var_ids[1]}']))
        self.assertEqual(product.get_variant_mapping(var_ids[2], supplier=supplier2), json.loads(data[f'variant_{supplier2.id}_{var_ids[2]}']))

        shipping = product.get_shipping_for_variant(supplier_id=supplier1.id, variant_id=var_ids[0], country_code='MA')
        self.assertIsNone(shipping)

        shipping = product.get_shipping_for_variant(supplier_id=supplier1.id, variant_id=var_ids[0], country_code='FR')
        self.assertEqual(shipping['country'], 'FR')
        self.assertEqual(shipping['method'], 'FEDEX_IE')

        shipping = product.get_shipping_for_variant(supplier_id=supplier1.id, variant_id=var_ids[0], country_code='US')
        self.assertEqual(shipping['country'], 'US')
        self.assertEqual(shipping['method'], 'EMS')

        shipping = product.get_shipping_for_variant(supplier_id=supplier1.id, variant_id=var_ids[1], country_code='CA')
        self.assertEqual(shipping['country'], 'CA')
        self.assertEqual(shipping['method'], 'EMS')
        self.assertEqual(shipping['method_name'], 'EMS ($37.49)')

        shipping = product.get_shipping_for_variant(supplier_id=supplier1.id, variant_id=var_ids[2], country_code='US')
        self.assertEqual(shipping['country'], 'US')
        self.assertEqual(shipping['method'], 'FEDEX_IE')

    @patch('last_seen.models.LastSeen.objects.when', Mock(return_value=True))
    def test_get_order_fulfill(self):
        self.user.profile.plan.permissions.add(AppPermissionFactory(name='orders.use', description=''))

        WooOrderTrackFactory(store=self.store, user=self.user, order_id=12345, line_id=777777, product_id=123)
        track = WooOrderTrackFactory(store=self.store, user=self.user, order_id=12346, line_id=777778, product_id=124)
        track.created_at = arrow.utcnow().replace(days=-2).datetime
        track.save()

        r = self.client.get('/api/woo/order-fulfill', {})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.json()), 2)

        r = self.client.get('/api/woo/order-fulfill', {'count_only': 'true'})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['pending'], 2)

        track = WooOrderTrackFactory(store=self.store, user=self.user, order_id=12347, line_id=777779, product_id=125)
        track.created_at = arrow.utcnow().replace(days=-3).datetime
        track.save()

        r = self.client.get('/api/woo/order-fulfill', {})
        self.assertEqual(len(r.json()), 3)

        date = arrow.utcnow().replace(days=-2).datetime
        r = self.client.get('/api/woo/order-fulfill', {'created_at': f'{date:%m/%d/%Y-}'})
        self.assertEqual(len(r.json()), 2)

        from_date, to_date = arrow.utcnow().replace(days=-3).datetime, arrow.utcnow().replace(days=-3).datetime
        r = self.client.get('/api/woo/order-fulfill', {'created_at': f'{from_date:%m/%d/%Y}-{to_date:%m/%d/%Y}'})
        self.assertEqual(len(r.json()), 1)
        self.assertEqual(r.json()[0]['id'], track.id)

    def test_delete_order_fulfill(self):
        track = WooOrderTrackFactory(user=self.user, store=self.store, product_id=123)

        r = self.client.delete(f'/api/woo/order-fulfill?order_id={track.order_id}&line_id={track.line_id}')
        self.assertEqual(r.status_code, 200)

        # OrderTrack doesn't exist
        self.assertFalse(self.store.wooordertrack_set.exists())

        # Empty search params
        r = self.client.delete('/api/woo/order-fulfill')
        self.assertEqual(r.status_code, 404)

        r = self.client.delete('/api/woo/order-fulfill?order_id=1&line_id=1')
        self.assertEqual(r.status_code, 404)

    @patch('woocommerce_core.utils.update_order_status')
    @patch('woocommerce_core.utils.get_shipping_carrier_name')
    @patch('woocommerce_core.models.WooStore.wcapi')
    def test_post_fulfill_order(self, wcapi_mock, get_shipping_carrier_name_mock, update_order_status_mock):
        track = WooOrderTrackFactory(user=self.user, store=self.store, product_id=123)
        data = {
            'fulfill-store': self.store.id,
            'fulfill-line-id': track.line_id,
            'fulfill-order-id': track.order_id,
            'fulfill-product-id': track.product_id,
            'fulfill-traking-number': 123,
            'fulfill-location-id': 1,
            'fulfill-tracking-link': 'https://www.ups.com/track?loc=en_US&tracknum=1223423413'
        }

        # Wrong tracking url
        get_shipping_carrier_name_mock.return_value = 'Custom Provider'
        r = self.client.post('/api/woo/fulfill-order', {**data, 'fulfill-tracking-link': 'htps://www.ups.com'})
        self.assertEqual(r.status_code, 500)
        self.assertIn('valid URL', r.json()['error'])

        # Incorrect shipping provider
        get_shipping_carrier_name_mock.return_value = None
        r = self.client.post('/api/woo/fulfill-order', data)
        self.assertEqual(r.status_code, 500)
        self.assertIn('Invalid shipping provider', r.json()['error'])

        # Items remaining fulfillment
        get_shipping_carrier_name_mock.return_value = 'Custom Provider'
        wcapi_mock.put = Mock(return_value=Mock(ok=True, json=Mock(return_value={
            'line_items': [{
                'meta_data': [{'key': 'Fulfillment Status', 'value': 'Unfulfilled'}]
            }]
        })))

        r = self.client.post('/api/woo/fulfill-order', data)
        self.assertEqual(r.status_code, 200)
        update_order_status_mock.assert_not_called()

        # All items fulfilled
        wcapi_mock.put = Mock(return_value=Mock(ok=True, json=Mock(return_value={
            'line_items': [{
                'meta_data': [{'key': 'Fulfillment Status', 'value': 'Fulfilled'}]
            }]
        })))

        r = self.client.post('/api/woo/fulfill-order', data)
        self.assertEqual(r.status_code, 200)
        update_order_status_mock.assert_called_with(self.store, track.order_id, 'completed')

    @patch('woocommerce_core.utils.WooOrderUpdater.delay_save', Mock(return_value=None))
    @patch('woocommerce_core.utils.update_order_status', Mock(return_value=None))
    @patch('woocommerce_core.models.WooStore.wcapi')
    def test_post_order_fulfill(self, wcapi_mock):
        track = WooOrderTrackFactory(user=self.user, store=self.store, product_id=123)

        data = {
            'store': self.store.id,
            'order_id': track.order_id,
            'line_id': track.line_id,
            'line_sku': '',
            'aliexpress_order_id': '123',
            'source_type': 'aliexpress',
        }

        wcapi_mock.get = Mock(return_value=Mock(ok=True, json=Mock(return_value={
            'line_items': [{
                'id': track.line_id, 'product_id': 123
            }]
        })))

        # Missing line_id
        r = self.client.post('/api/woo/order-fulfill', {**data, 'line_id': ''})
        self.assertEqual(r.status_code, 500)
        self.assertIn('input is missing', r.json()['error'])

        # Missing order_id
        r = self.client.post('/api/woo/order-fulfill', {**data, 'aliexpress_order_id': ''})
        self.assertEqual(r.status_code, 501)
        self.assertIn('empty', r.json()['error'].lower())

        r = self.client.post('/api/woo/order-fulfill', data)
        self.assertEqual(r.status_code, 200)

        track.refresh_from_db()
        self.assertEqual(track.source_id, data['aliexpress_order_id'])
        self.assertEqual(track.source_type, data['source_type'])

        # Already fulfilled
        r = self.client.post('/api/woo/order-fulfill', {**data, 'aliexpress_order_id': '1'})

        self.assertEqual(r.status_code, 422)
        self.assertIn('already', r.json().get('error'))

    @patch('woocommerce_core.models.WooProduct.sync')
    @patch('shopified_core.permissions.can_add_product')
    def test_post_import_product(self, can_add_product_mock, sync_mock):
        source_id = 12345678
        data = {
            'store': self.store.id,
            'product': source_id,
            'supplier': 'https://www.aliexpress.com/item/~/32961038442.html',
        }

        can_add_product_mock.return_value = [False, 1, 1]
        r = self.client.post('/api/woo/import-product', data)
        self.assertEqual(r.status_code, 401)
        can_add_product_mock.return_value = [True, 1, 1]

        r = self.client.post('/api/woo/import-product', data)
        self.assertEqual(r.status_code, 200)
        product = WooProduct.objects.get(id=r.json()['product'])
        self.assertEqual(product.source_id, source_id)
        self.assertTrue(product.has_supplier())

        r = self.client.post('/api/woo/import-product', data)
        self.assertEqual(r.status_code, 422)
        self.assertIn('connected', r.json().get('error'))

    @patch('shopified_core.utils.CancelledOrderAlert.send_email', Mock(return_value=None))
    def test_post_order_fulfill_update(self):
        track = WooOrderTrackFactory(user=self.user, store=self.store, product_id=123)
        data = {
            'store': self.store.id,
            'order': track.id,
            'source_id': '123',
            'tracking_number': '123',
            'status': 'PLACE_ORDER_SUCCESS',
            'end_reason': 'buyer_accept_goods',
            'order_details': json.dumps({})
        }

        r = self.client.post('/api/woo/order-fulfill-update', data)
        track.refresh_from_db()
        track_data = json.loads(track.data)

        self.assertEqual(r.status_code, 200)
        self.assertEqual(track.source_tracking, data['tracking_number'])
        self.assertEqual(track_data['aliexpress']['end_reason'], data['end_reason'])

    def test_delete_board_products(self):
        self.user.profile.plan.permissions.add(AppPermissionFactory(name='edit_product_boards.sub', description=''))
        board = WooBoardFactory(user=self.user)
        product = WooProductFactory(store=self.store, user=self.user)
        board.products.add(product)
        params = '?products[]={}&board_id={}'.format(product.id, board.id)
        r = self.client.delete('/api/woo/board-products' + params)
        self.assertEqual(r.status_code, 200)
        count = board.products.count()
        self.assertEqual(count, 0)

    def test_delete_board(self):
        self.user.profile.plan.permissions.add(AppPermissionFactory(name='edit_product_boards.sub', description=''))
        board = WooBoardFactory(user=self.user)
        params = '?board_id={}'.format(board.id)
        r = self.client.delete('/api/woo/board' + params)
        self.assertEqual(r.status_code, 200)
        count = self.user.wooboard_set.count()
        self.assertEqual(count, 0)

    def test_delete_product(self):
        self.user.profile.plan.permissions.add(AppPermissionFactory(name='delete_products.sub', description=''))
        product = WooProductFactory(store=self.store, user=self.user)
        params = '?product={}'.format(product.id)
        r = self.client.delete('/api/woo/product' + params)
        self.assertEqual(r.status_code, 200)
        count = self.user.wooproduct_set.count()
        self.assertEqual(count, 0)

    def test_delete_store(self):
        self.assertEqual(self.store.is_active, True)
        params = '?id={}'.format(self.store.id)
        r = self.client.delete('/api/woo/store' + params)
        self.assertEqual(r.status_code, 200)
        self.store.refresh_from_db()
        self.assertEqual(self.store.is_active, False)

    def test_delete_supplier(self):
        product = WooProductFactory(store=self.store, user=self.user, source_id=12345678)
        supplier1 = WooSupplierFactory(product=product)
        supplier2 = WooSupplierFactory(product=product)
        product.default_supplier = supplier1
        product.save()
        params = '?product={}&supplier={}'.format(product.id, supplier1.id)
        r = self.client.delete('/api/woo/supplier' + params)
        self.assertEqual(r.status_code, 200)
        count = product.woosupplier_set.count()
        self.assertEqual(count, 1)
        product.refresh_from_db()
        self.assertEqual(product.default_supplier, supplier2)

    def test_post_supplier_default(self):
        product = WooProductFactory(store=self.store, user=self.user, source_id=12345678)
        supplier = WooSupplierFactory(product=product)
        data = {'product': product.id, 'export': supplier.id}
        r = self.client.post('/api/woo/supplier-default', data)
        self.assertEqual(r.status_code, 200)
        product.refresh_from_db()
        self.assertEqual(product.default_supplier, supplier)

    def test_post_supplier(self):
        product = WooProductFactory(store=self.store, user=self.user, source_id=12345678)
        data = {
            'product': product.id,
            'original-link': '123',
            'supplier-link': '123',
            'supplier-name': 'test'
        }
        r = self.client.post('/api/woo/supplier', data)
        self.assertEqual(r.status_code, 200)
        product.refresh_from_db()
        count = product.woosupplier_set.count()
        self.assertEqual(count, 1)
        self.assertIsNotNone(product.default_supplier)

    @patch('woocommerce_core.tasks.product_export.apply_async')
    def test_post_product_export(self, product_export):
        product = WooProductFactory(store=self.store, user=self.user, source_id=12345678)
        data = {
            'store': self.store.id,
            'product': product.id,
            'publish': 'true',
        }
        r = self.client.post('/api/woo/product-export', data)
        self.assertEqual(r.status_code, 200)
        args = [self.store.id, product.id, self.user.id, True]
        product_export.assert_called_with(args=args, countdown=0, expires=120)

    @patch('woocommerce_core.tasks.product_save')
    def test_post_product_save(self, product_save):
        product_save.return_value = {}
        data = {
            'store': self.store.id,
            'data': json.dumps({
                'original_url': 'http://test.com',
                'title': 'Test Product',
                'store': {
                    'name': 'Test Store',
                    'url': 'http://teststore.com',
                },
            }),
        }
        r = self.client.post('/api/woo/product-save', data)
        self.assertEqual(r.status_code, 200)
        product_save.assert_called_once()

    @patch('woocommerce_core.tasks.product_update.apply_async')
    def test_post_product_update(self, product_update):
        product = WooProductFactory(store=self.store, user=self.user, source_id=12345678)
        product_data = {
            'original_url': 'http://test.com',
            'title': 'Test Product',
            'store': {
                'name': 'Test Store',
                'url': 'http://teststore.com',
            },
        }
        data = {
            'product': product.id,
            'data': json.dumps(product_data),
        }
        r = self.client.post('/api/woo/product-update', data)
        self.assertEqual(r.status_code, 200)
        product_update.assert_called_with(args=(product.id, product_data), countdown=0, expires=60)

    @patch('shopified_core.permissions.can_add_store', Mock(return_value=(True, 2, 0)))
    def test_post_store_add(self):
        data = {
            'title': 'Test Store',
            'api_url': 'https://woostore.com',
            'api_key': 'ck_323fce33402a70913e4cdbbdffa14bdb1cfb9a50',
            'api_password': 'cs_e32287eb90192ab2476015f9a69a30bb015dbdaf'
        }
        r = self.client.post('/api/woo/store-add', data)
        self.assertEqual(r.status_code, 200)
        count = self.user.woostore_set.count()
        self.assertEqual(count, 2)

    @patch('woocommerce_core.models.API.get')
    def test_get_store_verify(self, get_wcapi):
        r = self.client.get('/api/woo/store-verify', {'store': self.store.id})
        self.assertEqual(r.status_code, 200)
        get_wcapi.assert_called_once()
