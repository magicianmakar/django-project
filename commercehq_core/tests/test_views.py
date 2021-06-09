import json
from unittest.mock import patch, Mock, call as mock_call

import arrow
from munch import Munch

from lib.test import BaseTestCase, ProductAlertsBase
from django.urls import reverse
from django.test import tag
from django.core.cache import caches

from shopified_core.utils import order_data_cache
from leadgalaxy.models import SubuserPermission
from leadgalaxy.tests.factories import (
    UserFactory,
    GroupPlanFactory,
    AppPermissionFactory
)

from .factories import (
    CommerceHQBoardFactory,
    CommerceHQOrderTrackFactory,
    CommerceHQProductFactory,
    CommerceHQStoreFactory,
    CommerceHQSupplierFactory,
    ProductChangeFactory,
)
from ..models import CommerceHQStore, CommerceHQBoard, CommerceHQProduct


class StoreListTestCase(BaseTestCase):
    def setUp(self):
        self.user = UserFactory(username='test')
        self.password = 'test'
        self.user.set_password(self.password)
        self.user.save()

        self.user.profile.plan = GroupPlanFactory()
        permission = AppPermissionFactory(name='commercehq.use')
        self.user.profile.plan.permissions.add(permission)
        self.user.profile.save()

        self.path = reverse('index')

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
        self.assertTemplateUsed(r, 'home/index.html')

    def test_must_only_list_active_stores(self):
        CommerceHQStoreFactory(user=self.user, is_active=True)
        CommerceHQStoreFactory(user=self.user, is_active=False)
        self.login()
        r = self.client.get(self.path)
        self.assertEqual(len(r.context['user_stores']['all']), 1)

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
            'title': 'Dropified Test App',
            'api_url': 'http://chq-shopified-test.commercehqtesting.com/admin',
            'api_key': 'gsycAdWxbv56CAQFNWVkN53sLxnzcSEF',
            'api_password': 'euld-IWsmA1SkT5dved51decAcrXoz6n'}

        self.headers = {'HTTP_X_REQUESTED_WITH': 'XMLHttpRequest'}
        self.path = '/api/chq/store-add'

    def login(self):
        self.client.login(username=self.user.username, password=self.password)

    @tag('slow')
    @tag('excessive')
    @patch('shopified_core.permissions.can_add_store', Mock(return_value=(True, 2, 0)))
    def test_must_create_new_store(self):
        self.login()
        r = self.client.post(self.path, self.data, **self.headers)
        self.assertEqual(r.reason_phrase, 'OK')

    @tag('slow')
    @tag('excessive')
    @patch('shopified_core.permissions.can_add_store', Mock(return_value=(True, 2, 0)))
    def test_must_add_store_to_user(self):
        self.login()
        r = self.client.post(self.path, self.data, **self.headers)

        store = CommerceHQStore.objects.first()

        self.assertEqual(store.user, self.user)
        self.assertEqual(r.reason_phrase, 'OK')

    @patch('shopified_core.permissions.can_add_store', Mock(return_value=(True, 2, 0)))
    def test_add_store_wrong_api_url(self):
        self.login()

        self.data['api_url'] = 'https://chq-shopified-test.commerce.com/admin'

        r = self.client.post(self.path, self.data, **self.headers)
        rep = json.loads(r.content)

        self.assertIn('stores URL is not correct', rep.get('error'))
        self.assertNotEqual(r.reason_phrase, 'OK')

    @tag('slow')
    @patch('shopified_core.permissions.can_add_store', Mock(return_value=(True, 2, 0)))
    def test_add_store_wrong_api_keys(self):
        self.login()

        self.data['api_key'] = '123456789'

        r = self.client.post(self.path, self.data, **self.headers)
        rep = json.loads(r.content)

        self.assertIn('API Credentials are incorrect', rep.get('error'))
        self.assertNotEqual(r.reason_phrase, 'OK')

    @patch('shopified_core.permissions.can_add_store', Mock(return_value=(True, 2, 0)))
    def test_must_not_allow_subusers_to_create(self):
        self.client.login(username=self.subuser.username, password=self.subuser_password)
        r = self.client.post(self.path, self.data, **self.headers)
        self.assertIn(r.status_code, [401, 403])


class StoreUpdateTestCase(BaseTestCase):
    def setUp(self):
        self.user = UserFactory(username='test')
        self.password = 'test'
        self.user.set_password(self.password)
        self.user.save()
        self.store = CommerceHQStoreFactory(user=self.user)

        self.subuser = UserFactory()
        self.subuser_password = 'test'
        self.subuser.set_password(self.subuser_password)
        self.subuser.save()
        self.subuser.profile.subuser_parent = self.user
        self.subuser.profile.save()

        self.data = {
            'title': 'Test Store',
            'api_url': 'https://example.commercehq.com',
            'api_key': 'testkey',
            'api_password': 'testpassword'}

        self.headers = {'HTTP_X_REQUESTED_WITH': 'XMLHttpRequest'}
        self.path = reverse('chq:store_update', args=(self.store.pk,))

    def login(self):
        self.client.login(username=self.user.username, password=self.password)

    def test_must_be_logged_in(self):
        r = self.client.get(self.path, **self.headers)
        self.assertEqual(r.status_code, 401)

    def test_must_return_correct_form_template(self):
        self.login()
        r = self.client.get(self.path, **self.headers)
        self.assertTrue(r.status_code, 200)
        self.assertTemplateUsed(r, 'commercehq/partial/store_update_form.html')

    def test_must_update_store(self):
        self.login()
        r = self.client.post(self.path, self.data, **self.headers)
        self.store.refresh_from_db()
        self.assertEqual(r.status_code, 204)
        self.assertTrue(self.store.title, self.data['title'])

    def test_must_not_allow_subusers_to_update(self):
        self.client.login(username=self.subuser.username, password=self.subuser_password)
        r = self.client.post(self.path, self.data, **self.headers)
        self.assertEqual(r.status_code, 403)


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

        self.store = CommerceHQStoreFactory(user=self.user)
        self.headers = {'HTTP_X_REQUESTED_WITH': 'XMLHttpRequest'}
        self.path = '/api/chq/store?store_id=%s' % self.store.pk

    def test_must_be_logged_in(self):
        r = self.client.delete(self.path, **self.headers)
        self.assertEqual(r.status_code, 401)

    def test_user_must_be_able_to_delete_own_store(self):
        self.client.login(username=self.user.username, password=self.password)
        self.client.delete(self.path, **self.headers)
        count = self.user.commercehqstore_set.filter(is_active=True).count()
        self.assertEqual(count, 0)

    def test_must_not_allow_subusers_to_delete(self):
        self.client.login(username=self.subuser.username, password=self.subuser_password)
        r = self.client.delete(self.path, **self.headers)
        self.assertEqual(r.status_code, 403)


class BoardsListTestCase(BaseTestCase):
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

        self.path = reverse('chq:boards_list')

    def login(self):
        self.client.login(username=self.user.username, password=self.password)

    def subuser_login(self):
        self.client.login(username=self.subuser.username, password=self.subuser_password)

    def test_must_be_logged_in(self):
        r = self.client.get(self.path)
        self.assertRedirects(r, '%s?next=%s' % (reverse('login'), self.path))

    def test_must_return_ok(self):
        self.login()
        r = self.client.get(self.path)
        self.assertEqual(r.status_code, 200)

    def test_must_used_correct_template(self):
        self.login()
        r = self.client.get(self.path)
        self.assertTemplateUsed(r, 'commercehq/boards_list.html')

    def test_must_return_boards_of_user(self):
        CommerceHQBoardFactory(user=self.user)
        CommerceHQBoardFactory()
        self.login()
        r = self.client.get(self.path)
        boards = list(r.context['boards'])
        board = boards.pop()
        self.assertEqual(board.user, self.user)
        self.assertEqual(len(boards), 0)

    def test_subuser_cant_access_without_permission(self):
        self.subuser_login()
        r = self.client.get(self.path)
        self.assertEqual(r.status_code, 403)

    def test_subuser_can_access_with_permission(self):
        self.subuser.profile.have_global_permissions()
        self.subuser_login()
        r = self.client.get(self.path)

        if SubuserPermission.objects.count():
            self.assertEqual(r.status_code, 200)
        else:
            self.assertEqual(r.status_code, 403)


class BoardCreateTestCase(BaseTestCase):
    def setUp(self):
        self.user = UserFactory(username='test')
        self.password = 'test'
        self.user.set_password(self.password)
        self.user.save()
        self.path = '/api/chq/boards-add'
        self.data = {'title': 'Test Board'}
        self.headers = {'HTTP_X_REQUESTED_WITH': 'XMLHttpRequest'}

    def login(self):
        self.client.login(username=self.user.username, password=self.password)

    def test_must_require_requests_to_be_ajax(self):
        r = self.client.post(self.path, self.data)
        self.assertEqual(r.status_code, 401)

    def test_must_be_logged_in(self):
        r = self.client.post(self.path, self.data, **self.headers)
        self.assertEqual(r.status_code, 401)

    @patch('commercehq_core.api.permissions.can_add_board', Mock(return_value=(True, True, True)))
    def test_must_create_new_board(self):
        self.login()
        r = self.client.post(self.path, self.data, **self.headers)
        self.assertEqual(r.status_code, 200)

    @patch('commercehq_core.api.permissions.can_add_board', Mock(return_value=(True, True, True)))
    def test_must_add_board_to_user(self):
        self.login()
        self.client.post(self.path, self.data, **self.headers)
        board = CommerceHQBoard.objects.get(title=self.data['title'])
        self.assertEqual(board.user, self.user)

    @patch('commercehq_core.api.permissions.can_add_board', Mock(return_value=(True, True, True)))
    def test_board_name_is_required(self):
        self.login()
        r = self.client.post(self.path, {'title': ''}, **self.headers)
        self.assertEqual(r.status_code, 501)


class BoardUpdateTestCase(BaseTestCase):
    def setUp(self):
        self.user = UserFactory(username='test')
        self.password = 'test'
        self.user.set_password(self.password)
        self.user.save()
        self.board = CommerceHQBoardFactory(user=self.user)

        self.data = {
            'board_id': self.board.pk,
            'title': 'Test Board',
            'product_title': 'Test Product Title',
            'product_tags': 'hello,there',
            'product_type': 'Test Type'}

        self.headers = {'HTTP_X_REQUESTED_WITH': 'XMLHttpRequest'}
        self.path = '/api/chq/board-config'

    def login(self):
        self.client.login(username=self.user.username, password=self.password)

    def test_must_require_requests_to_be_ajax(self):
        r = self.client.get(self.path)
        self.assertEqual(r.status_code, 401)

    def test_must_be_logged_in(self):
        r = self.client.get(self.path, **self.headers)
        self.assertEqual(r.status_code, 401)

    def test_must_update_board(self):
        self.login()
        r = self.client.post(self.path, self.data, **self.headers)
        self.board.refresh_from_db()
        new_config = json.loads(self.board.config)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.board.title, self.data['title'])
        self.assertEqual(new_config['title'], self.data['product_title'])
        self.assertEqual(new_config['tags'], self.data['product_tags'])
        self.assertEqual(new_config['type'], self.data['product_type'])

    def test_must_not_return_data_of_other_users_board(self):
        board = CommerceHQBoardFactory()
        self.login()
        r = self.client.get(self.path, data={'board_id': board.pk})
        self.assertEqual(r.status_code, 403)


class BoardDeleteTestCase(BaseTestCase):
    def setUp(self):
        self.user = UserFactory(username='test')
        self.password = 'test'
        self.user.set_password(self.password)
        self.user.save()

        self.board = CommerceHQBoardFactory(user=self.user)
        self.headers = {'HTTP_X_REQUESTED_WITH': 'XMLHttpRequest'}
        self.path = '/api/chq/board?board_id=%s' % self.board.pk

    def test_must_be_logged_in(self):
        r = self.client.delete(self.path, **self.headers)
        self.assertEqual(r.status_code, 401)

    def test_user_must_be_able_to_delete_own_board(self):
        self.client.login(username=self.user.username, password=self.password)
        r = self.client.delete(self.path, **self.headers)
        count = self.user.commercehqboard_set.count()
        self.assertEqual(count, 0)
        self.assertEqual(r.status_code, 200)


class BoardEmptyTestCase(BaseTestCase):
    def setUp(self):
        self.user = UserFactory(username='test')
        self.password = 'test'
        self.user.set_password(self.password)
        self.user.save()

        self.store = CommerceHQStoreFactory(user=self.user)
        self.board = CommerceHQBoardFactory(user=self.user)
        self.product = CommerceHQProductFactory(user=self.user, store=self.store)
        self.board.products.add(self.product)
        self.headers = {'HTTP_X_REQUESTED_WITH': 'XMLHttpRequest'}
        self.path = '/api/chq/board-empty'

    def test_must_be_logged_in(self):
        r = self.client.post(self.path, data={'board_id': self.board.pk}, **self.headers)
        self.assertEqual(r.status_code, 401)

    def test_user_must_be_able_to_empty_own_board(self):
        self.client.login(username=self.user.username, password=self.password)
        self.client.post(self.path, data={'board_id': self.board.pk}, **self.headers)
        count = self.board.products.count()
        self.assertEqual(count, 0)


class BoardDetailTestCase(BaseTestCase):
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

        self.board = CommerceHQBoardFactory(user=self.user, title='Test Board')
        self.board2 = CommerceHQBoardFactory(title='Test Board2')
        self.path = reverse('chq:board_detail', args=(self.board.pk,))

    def login(self):
        self.client.login(username=self.user.username, password=self.password)

    def subuser_login(self):
        self.client.login(username=self.subuser.username, password=self.subuser_password)

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
        self.assertTemplateUsed(r, 'commercehq/board.html')

    def test_must_have_board_in_context(self):
        self.login()
        r = self.client.get(self.path)
        self.assertIn('board', r.context)

    def test_must_only_show_own_board(self):
        self.login()
        r = self.client.get(reverse('chq:board_detail', kwargs={'pk': self.board2.id}))
        self.assertEqual(r.status_code, 404)

    def test_must_have_breadcrumbs(self):
        self.login()
        r = self.client.get(self.path)
        boards_breadcrumb = {'title': 'Boards', 'url': reverse('chq:boards_list')}
        self.assertEqual(r.context['breadcrumbs'], [boards_breadcrumb, self.board.title])

    def test_subuser_cant_access_without_permission(self):
        self.subuser_login()
        r = self.client.get(self.path)
        self.assertEqual(r.status_code, 403)

    def test_subuser_can_access_with_permission(self):
        self.subuser.profile.have_global_permissions()
        self.subuser_login()
        r = self.client.get(self.path)

        if SubuserPermission.objects.count():
            self.assertEqual(r.status_code, 200)
        else:
            self.assertEqual(r.status_code, 403)


class CommerceHQProductTestCase(BaseTestCase):
    def test_get_original_info(self):
        product = CommerceHQProductFactory()
        self.assertIs(product.get_original_info(), None)

        product = CommerceHQProductFactory()
        supplier = CommerceHQSupplierFactory(product=product)
        supplier.product_url = 'http://www.aliexpress.com/123'
        product.default_supplier = supplier
        product.save()

        expected = {
            'domain': 'aliexpress',
            'source': 'Aliexpress',
            'url': supplier.product_url,
        }

        self.assertDictEqual(product.get_original_info(), expected)


class SubuserpermissionsApiTestCase(BaseTestCase):
    def setUp(self):
        self.error_message = "Permission Denied: You don't have permission to perform this action"
        self.parent_user = UserFactory()
        self.parent_user.profile.plan.permissions.add(AppPermissionFactory(name='send_to_store.use', description=''))
        self.user = UserFactory()
        self.user.profile.subuser_parent = self.parent_user
        self.user.profile.save()
        self.password = 'test'
        self.user.set_password(self.password)
        self.user.save()
        self.store = CommerceHQStoreFactory(user=self.parent_user)
        self.headers = {'HTTP_X_REQUESTED_WITH': 'XMLHttpRequest'}
        self.client.login(username=self.user.username, password=self.password)

    @patch('commercehq_core.api.permissions.user_can_edit', Mock(return_value=True))
    def test_subuser_can_view_board_with_permission(self):
        self.user.profile.have_global_permissions()
        board = CommerceHQBoardFactory(user=self.user)
        data = {'board_id': board.pk}
        r = self.client.get('/api/chq/board-config', data, **self.headers)

        if SubuserPermission.objects.count():
            self.assertEqual(r.status_code, 200)
        else:
            self.assertEqual(r.status_code, 403)

    @patch('commercehq_core.api.permissions.user_can_edit', Mock(return_value=True))
    def test_subuser_cannot_view_board_without_permission(self):
        board = CommerceHQBoardFactory(user=self.user)
        data = {'board_id': board.pk}
        r = self.client.get('/api/chq/board-config', data, **self.headers)
        self.assertEqual(r.status_code, 403)

    @patch('commercehq_core.api.permissions.can_add_board', Mock(return_value=(True, True, True)))
    @patch('commercehq_core.api.permissions.user_can_add', Mock(return_value=True))
    def test_subuser_can_add_board_with_permission(self):
        self.user.profile.have_global_permissions()
        data = {'title': 'test'}
        r = self.client.post('/api/chq/boards-add', data, **self.headers)

        if SubuserPermission.objects.count():
            self.assertEqual(r.status_code, 200)
        else:
            self.assertEqual(r.status_code, 403)

    @patch('commercehq_core.api.permissions.can_add_board', Mock(return_value=(True, True, True)))
    @patch('commercehq_core.api.permissions.user_can_add', Mock(return_value=True))
    def test_subuser_cannot_add_board_without_permission(self):
        data = {'title': 'test'}
        r = self.client.post('/api/chq/boards-add', data, **self.headers)
        self.assertEqual(r.status_code, 403)

    @patch('commercehq_core.api.permissions.user_can_edit', Mock(return_value=True))
    def test_subuser_can_add_product_to_board_with_permission(self):
        self.user.profile.have_global_permissions()
        board = CommerceHQBoardFactory(user=self.user)
        product = CommerceHQProductFactory(store=self.store, user=self.parent_user)
        data = {'product': product.id, 'board': board.id}
        r = self.client.post('/api/chq/product-board', data, **self.headers)

        if SubuserPermission.objects.count():
            self.assertEqual(r.status_code, 200)
        else:
            self.assertEqual(r.status_code, 403)

    @patch('commercehq_core.api.permissions.user_can_edit', Mock(return_value=True))
    def test_subuser_cannot_add_product_to_board_without_permission(self):
        board = CommerceHQBoardFactory(user=self.user)
        product = CommerceHQProductFactory(store=self.store, user=self.parent_user)
        data = {'product': product.id, 'board': board.id}
        r = self.client.post('/api/chq/product-board', data, **self.headers)
        self.assertEqual(r.status_code, 403)

    @patch('commercehq_core.api.permissions.user_can_edit', Mock(return_value=True))
    def test_subuser_can_remove_product_from_board_with_permission(self):
        self.user.profile.have_global_permissions()
        board = CommerceHQBoardFactory(user=self.user)
        product = CommerceHQProductFactory(store=self.store, user=self.parent_user)
        board.products.add(product)
        params = '?products={}&board_id={}'.format(product.id, board.id)
        r = self.client.delete('/api/chq/board-products' + params, **self.headers)

        if SubuserPermission.objects.count():
            self.assertEqual(r.status_code, 200)
        else:
            self.assertEqual(r.status_code, 403)

    @patch('commercehq_core.api.permissions.user_can_edit', Mock(return_value=True))
    def test_subuser_cannot_remove_product_from_board_without_permission(self):
        board = CommerceHQBoardFactory(user=self.user)
        product = CommerceHQProductFactory(store=self.store, user=self.parent_user)
        board.products.add(product)
        params = '?products={}&board_id={}'.format(product.id, board.id)
        r = self.client.delete('/api/chq/board-products' + params, **self.headers)
        self.assertEqual(r.status_code, 403)

    @patch('commercehq_core.api.permissions.user_can_delete', Mock(return_value=True))
    def test_subuser_can_delete_board_with_permission(self):
        self.user.profile.have_global_permissions()
        board = CommerceHQBoardFactory(user=self.user)
        params = '?board_id={}'.format(board.id)
        r = self.client.delete('/api/chq/board' + params, **self.headers)

        if SubuserPermission.objects.count():
            self.assertFalse(CommerceHQBoard.objects.filter(pk=board.id).exists())
            self.assertEqual(r.status_code, 200)
        else:
            self.assertEqual(r.status_code, 403)

    @patch('commercehq_core.api.permissions.user_can_delete', Mock(return_value=True))
    def test_subuser_cannot_delete_board_without_permission(self):
        board = CommerceHQBoardFactory(user=self.user)
        params = '?board_id={}'.format(board.id)
        r = self.client.delete('/api/chq/board' + params, **self.headers)
        self.assertEqual(r.status_code, 403)

    @patch('commercehq_core.api.permissions.user_can_edit', Mock(return_value=True))
    def test_subuser_can_empty_board_with_permission(self):
        self.user.profile.have_global_permissions()
        board = CommerceHQBoardFactory(user=self.user)
        data = {'board_id': board.id}
        r = self.client.post('/api/chq/board-empty', data, **self.headers)

        if SubuserPermission.objects.count():
            self.assertEqual(r.status_code, 200)
        else:
            self.assertEqual(r.status_code, 403)

    @patch('commercehq_core.api.permissions.user_can_edit', Mock(return_value=True))
    def test_subuser_cannot_empty_board_without_permission(self):
        board = CommerceHQBoardFactory(user=self.user)
        data = {'board_id': board.id}
        r = self.client.post('/api/chq/board-empty', data, **self.headers)
        self.assertEqual(r.status_code, 403)

    @patch('commercehq_core.api.permissions.user_can_edit', Mock(return_value=True))
    def test_subuser_can_edit_board_config_with_permission(self):
        self.user.profile.have_global_permissions()
        board = CommerceHQBoardFactory(user=self.user)
        data = {'board_id': board.id, 'title': 'test'}
        r = self.client.post('/api/chq/board-config', data, **self.headers)

        if SubuserPermission.objects.count():
            self.assertEqual(r.status_code, 200)
        else:
            self.assertEqual(r.status_code, 403)

    @patch('commercehq_core.api.permissions.user_can_edit', Mock(return_value=True))
    def test_subuser_cannot_edit_board_config_without_permission(self):
        board = CommerceHQBoardFactory(user=self.user)
        data = {'board_id': board.id, 'title': 'test'}
        r = self.client.post('/api/chq/board-config', data, **self.headers)
        self.assertEqual(r.status_code, 403)

    @patch('commercehq_core.tasks.product_save', Mock(return_value=None))
    def test_subuser_can_not_save_for_later_with_permission(self):
        self.user.profile.subuser_chq_stores.remove(self.store)
        data = {'store': self.store.id}
        r = self.client.post('/api/chq/save-for-later', data, **self.headers)
        self.assertEqual(r.status_code, 403)

    @patch('commercehq_core.tasks.product_save', Mock(return_value=None))
    def test_subuser_cant_save_for_later_without_permission(self):
        self.user.profile.subuser_chq_stores.add(self.store)
        permission = self.user.profile.subuser_chq_permissions.get(codename='save_for_later')
        self.user.profile.subuser_chq_permissions.remove(permission)
        data = {'store': self.store.id}
        r = self.client.post('/api/chq/save-for-later', data, **self.headers)
        self.assertEqual(r.status_code, 403)

    @patch('commercehq_core.tasks.product_export.apply_async', Mock(return_value=None))
    @patch('commercehq_core.api.permissions.user_can_view', Mock(return_value=True))
    def test_subuser_can_send_to_chq_with_permission(self):
        product = CommerceHQProductFactory(user=self.parent_user)
        self.store.products.add(product)
        self.user.profile.subuser_chq_stores.add(self.store)
        data = {'store': self.store.id, 'product': product.id, 'publish': False}
        r = self.client.post('/api/chq/product-export', data, **self.headers)
        self.assertEqual(r.status_code, 200)

    @patch('commercehq_core.tasks.product_export.apply_async', Mock(return_value=None))
    @patch('commercehq_core.api.permissions.user_can_view', Mock(return_value=True))
    def test_subuser_cant_send_to_chq_without_permission(self):
        product = CommerceHQProductFactory(user=self.parent_user)
        self.store.products.add(product)
        self.user.profile.subuser_chq_stores.add(self.store)
        permission = self.user.profile.subuser_chq_permissions.get(codename='send_to_chq')
        self.user.profile.subuser_chq_permissions.remove(permission)
        data = {'store': self.store.id, 'product': product.id, 'publish': False}
        r = self.client.post('/api/chq/product-export', data, **self.headers)
        self.assertEqual(r.status_code, 403)

    @patch('commercehq_core.api.permissions.user_can_delete', Mock(return_value=True))
    def test_subuser_can_delete_products_with_permission(self):
        product = CommerceHQProductFactory(user=self.parent_user)
        self.store.products.add(product)
        self.user.profile.subuser_chq_stores.add(self.store)
        params = '?product={}'.format(product.id)
        r = self.client.delete('/api/chq/product' + params, **self.headers)
        self.assertEqual(r.status_code, 200)

    @patch('commercehq_core.api.permissions.user_can_delete', Mock(return_value=True))
    def test_subuser_cant_delete_products_without_permission(self):
        product = CommerceHQProductFactory(user=self.parent_user)
        self.store.products.add(product)
        self.user.profile.subuser_chq_stores.add(self.store)
        permission = self.user.profile.subuser_chq_permissions.get(codename='delete_products')
        self.user.profile.subuser_chq_permissions.remove(permission)
        params = '?product={}'.format(product.id)
        r = self.client.delete('/api/chq/product' + params, **self.headers)
        self.assertEqual(r.status_code, 403)

    def test_subuser_cant_fulfill_order_without_permission(self):
        self.user.profile.subuser_chq_stores.add(self.store)
        permission = self.user.profile.subuser_chq_permissions.get(codename='place_orders')
        self.user.profile.subuser_chq_permissions.remove(permission)
        data = {'store': self.store.id}
        r = self.client.post('/api/chq/order-fulfill', data, **self.headers)
        self.assertEqual(r.status_code, 403)

    def test_subuser_cant_update_order_fulfillment_without_permission(self):
        self.user.profile.subuser_chq_stores.add(self.store)
        permission = self.user.profile.subuser_chq_permissions.get(codename='place_orders')
        self.user.profile.subuser_chq_permissions.remove(permission)
        data = {'store': self.store.id}
        r = self.client.post('/api/chq/order-fulfill-update', data, **self.headers)
        self.assertEqual(r.status_code, 403)


class ProductAlertsTestCase(ProductAlertsBase):
    store_factory = CommerceHQStoreFactory
    product_factory = CommerceHQProductFactory
    supplier_factory = CommerceHQSupplierFactory
    change_factory = ProductChangeFactory

    def setUp(self):
        super().setUp()
        self.subuser.profile.subuser_chq_stores.add(self.store)

        self.product_change1 = self.change_factory(
            chq_product=self.product,
            user=self.user,
            store_type='chq',
            data=self.change_data1,
        )

        self.product_change2 = self.change_factory(
            chq_product=self.product,
            user=self.user,
            store_type='chq',
            data=self.change_data2,
        )

    def test_subuser_can_access_alerts(self):
        self.subuser.profile.have_global_permissions()
        self.client.force_login(self.subuser)

        path = reverse('chq:product_alerts')
        with patch('commercehq_core.utils.get_chq_products',
                   return_value=[{'id': self.product.source_id}]):
            response = self.client.get(path)

        text = response.content.decode()
        key = 'Is now <b style="color:green">Online</b>'

        self.assertEqual(text.count(key), 2)


class ApiTestCase(BaseTestCase):
    def setUp(self):
        self.parent_user = UserFactory()
        self.user = UserFactory()
        self.password = 'test'
        self.user.set_password(self.password)
        self.user.save()

        self.store = CommerceHQStoreFactory(user=self.user)
        self.client.login(username=self.user.username, password=self.password)

    @patch('commercehq_core.models.CommerceHQProduct.retrieve')
    def test_post_product_connect(self, product_retrieve):
        product = CommerceHQProductFactory(
            store=self.store, user=self.user, source_id=12345678,
            data='''{
            "tags": [],
            "images": [],
            "textareas": [{"name": "Description", "text": "Ok"}],
            "is_multi": false,
            "price": 10.00,
            "compare_price": 10.00,
            "shipping_weight": "",
            "is_draft": "",
            "store": {
                "name": "Suplier 1",
                "url": "https://www.aliexpress.com/item/12345467890.html"
            }}''')

        def retrieve():
            return product.parsed

        product_retrieve.side_effect = retrieve

        data = {'product': product.id, 'store': self.store.id, 'shopify': 12345670001}
        r = self.client.post('/api/chq/product-connect', data)
        self.assertEqual(r.status_code, 200)
        product_retrieve.assert_called_once()

        product.refresh_from_db()
        self.assertEqual(product.source_id, data['shopify'])

    @patch('commercehq_core.utils.duplicate_product')
    def test_post_product_duplicate(self, duplicate_product):
        duplicate_product_id = 1111222
        duplicate_product.return_value = Munch({'id': duplicate_product_id})
        product = CommerceHQProductFactory(
            store=self.store, user=self.user, source_id=12345678,
            data='''{"store": {
                "name": "Suplier 1",
                "url": "https://www.aliexpress.com/item/12345467890.html"
            }}''')

        data = {'product': product.id}
        r = self.client.post('/api/chq/product-duplicate', data)
        self.assertEqual(r.status_code, 200)

        self.assertEqual(r.json()['product']['id'], duplicate_product_id)
        self.assertEqual(r.json()['product']['url'], f'/chq/product/{duplicate_product_id}')

        duplicate_product.assert_called_with(product)

    @patch('commercehq_core.utils.set_chq_order_note')
    def test_post_order_note(self, set_chq_order_note):
        order_id = '123456789'
        note = 'Test Note'
        data = {'store': self.store.id, 'order_id': order_id, 'note': note}

        r = self.client.post('/api/chq/order-note', data)
        self.assertEqual(r.status_code, 200)

        set_chq_order_note.assert_called_with(self.store, order_id, note)

    @patch('commercehq_core.tasks.create_image_zip.apply_async')
    def test_get_product_image_download(self, create_image_zip):
        product = CommerceHQProductFactory(
            store=self.store, user=self.user, source_id=12345678,
            data='''{"store": {
                "name": "Suplier 1",
                "url": "https://www.aliexpress.com/item/12345467890.html"
            }}''')

        data = {'product': product.id}

        r = self.client.get('/api/chq/product-image-download', data)
        self.assertEqual(r.status_code, 422)
        self.assertIn(r.json()['error'], 'Product doesn\'t have any images')

        create_image_zip.assert_not_called()

        images = ["http://www.aliexpress.com/image/1.png"]
        product = CommerceHQProductFactory(
            store=self.store, user=self.user, source_id=12345678,
            data=json.dumps({"images": images}))

        data = {'product': product.id}
        r = self.client.get('/api/chq/product-image-download', data)
        self.assertEqual(r.status_code, 200)

        create_image_zip.assert_called_with(args=[images, product.id], countdown=5)

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
            "solve": True
        }

        caches['orders'].set(f'order_{order_key}', data)
        self.assertIsNotNone(caches['orders'].get(f'order_{order_key}'))
        self.assertIsNotNone(order_data_cache(f'order_{order_key}'))
        self.assertIsNotNone(order_data_cache(f'{order_key}'))
        self.assertIsNotNone(order_data_cache(self.store.id, order_id, line_id))

        # Store not found
        r = self.client.get('/api/chq/order-data', {'order': f'444{order_key}'})
        self.assertEqual(r.status_code, 404)
        self.assertIn('Store not found', r.content.decode())

        # Order not found
        r = self.client.get('/api/chq/order-data', {'order': f'{order_key}5455'})
        self.assertEqual(r.status_code, 404)
        self.assertIn('Not found:', r.content.decode())

        # Key order prefix is present
        r = self.client.get('/api/chq/order-data', {'order': f'order_{order_key}'})
        self.assertEqual(r.status_code, 200)
        api_data = r.json()
        if api_data.get('status'):
            data['status'] = api_data['status']

        self.assertEqual(json.dumps(api_data, indent=2), json.dumps(data, indent=2))

        # Key prefix removed (default)
        r = self.client.get('/api/chq/order-data', {'order': f'{order_key}'})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), data)
        self.assertFalse(r.json()['ordered'])

        # Test aliexpress_country_code_map
        data['shipping_address']['country_code'] = 'GB'
        caches['orders'].set(f'order_{order_key}', data)

        r = self.client.get('/api/chq/order-data', {'order': f'{order_key}'})
        self.assertEqual(r.status_code, 200)
        self.assertNotEqual(r.json()['shipping_address']['country_code'], data['shipping_address']['country_code'])
        self.assertEqual(r.json()['shipping_address']['country_code'], 'UK')

        # Order Track exist
        CommerceHQOrderTrackFactory(user=self.user, store=self.store, order_id=order_id, line_id=line_id)

        r = self.client.get('/api/chq/order-data', {'order': f'{order_key}'})
        ordered = r.json()['ordered']
        self.assertEqual(r.status_code, 200)
        self.assertEqual(type(ordered), dict)
        self.assertIn('time', ordered)
        self.assertIn('link', ordered)

    def test_post_variants_mapping(self):
        product = CommerceHQProductFactory(
            store=self.store, user=self.user, source_id=12345678,
            data='''{"store": {
                "name": "Suplier 1",
                "url": "https://www.aliexpress.com/item/12345467890.html"
            }}''')

        supplier = CommerceHQSupplierFactory(product=product)

        product.default_supplier = supplier
        product.save()

        var_id = '18395643215934'
        data = {
            'product': product.id,
            'supplier': supplier.id,
            var_id: '[{"title":"China","sku":"sku-1-201336100"}]',
        }

        r = self.client.post('/api/chq/variants-mapping', data)
        self.assertEqual(r.status_code, 200)

        product.refresh_from_db()
        supplier.refresh_from_db()

        self.assertEqual(product.get_variant_mapping(var_id), json.loads(data[var_id]))
        self.assertEqual(product.get_variant_mapping(var_id, for_extension=True), json.loads(data[var_id]))

    def test_post_suppliers_mapping(self):
        self.user.profile.plan.permissions.add(
            AppPermissionFactory(name='suppliers_shipping_mapping.use')
        )
        self.user.profile.save()

        product = CommerceHQProductFactory(
            store=self.store, user=self.user, source_id=12345678,
            data='''{"store": {
                "name": "Suplier 1",
                "url": "https://www.aliexpress.com/item/12345467890.html"
            }}''')

        supplier1 = CommerceHQSupplierFactory(product=product)
        supplier2 = CommerceHQSupplierFactory(product=product)

        product.set_default_supplier(supplier1)

        var_ids = ['18401388822590', '18401388888126', '18401388855358']
        data = {
            'config': 'default',
            'product': product.id,
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

        r = self.client.post('/api/chq/suppliers-mapping', data)
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

        CommerceHQOrderTrackFactory(store=self.store, user=self.user, order_id=12345, line_id=777777)
        track = CommerceHQOrderTrackFactory(store=self.store, user=self.user, order_id=12346, line_id=777778)
        track.created_at = arrow.utcnow().replace(days=-2).datetime
        track.save()

        r = self.client.get('/api/chq/order-fulfill', {})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.json()), 2)

        r = self.client.get('/api/chq/order-fulfill', {'count_only': 'true'})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['pending'], 2)

        track = CommerceHQOrderTrackFactory(store=self.store, user=self.user, order_id=12347, line_id=777779)
        track.created_at = arrow.utcnow().replace(days=-3).datetime
        track.save()

        r = self.client.get('/api/chq/order-fulfill', {})
        self.assertEqual(len(r.json()), 3)

        date = arrow.utcnow().replace(days=-2).datetime
        r = self.client.get('/api/chq/order-fulfill', {'created_at': f'{date:%m/%d/%Y-}'})
        self.assertEqual(len(r.json()), 2)

        from_date, to_date = arrow.utcnow().replace(days=-3).datetime, arrow.utcnow().replace(days=-3).datetime
        r = self.client.get('/api/chq/order-fulfill', {'created_at': f'{from_date:%m/%d/%Y}-{to_date:%m/%d/%Y}'})
        self.assertEqual(len(r.json()), 1)
        self.assertEqual(r.json()[0]['id'], track.id)

    @patch('commercehq_core.models.CommerceHQStore.request', Mock(patch=Mock(return_value=None)))
    def test_delete_order_fulfill(self):
        track = CommerceHQOrderTrackFactory(user=self.user, store=self.store)

        r = self.client.delete(f'/api/chq/order-fulfill?order_id={track.order_id}&line_id={track.line_id}')
        self.assertEqual(r.status_code, 200)

        # OrderTrack doesn't exist
        self.assertFalse(self.store.commercehqordertrack_set.exists())

        # Empty search params
        r = self.client.delete('/api/shopify/order-fulfill')
        self.assertEqual(r.status_code, 404)

        r = self.client.delete('/api/shopify/order-fulfill?order_id=1&line_id=1')
        self.assertEqual(r.status_code, 404)

    @patch('commercehq_core.models.CommerceHQStore.request')
    def test_post_fulfill_order(self, requests_mock):
        track = CommerceHQOrderTrackFactory(user=self.user, store=self.store)
        data = {
            'fulfill-store': self.store.id,
            'fulfill-line-id': track.line_id,
            'fulfill-order-id': track.order_id,
            'fulfill-traking-number': 123,
            'fulfill-location-id': 1
        }

        # UNSUPPORTED: Inventory tracking enabled
        requests_mock.post = Mock(return_value=Mock(ok=False, text='Warehouse ID'))
        r = self.client.post('/api/chq/fulfill-order', data)

        requests_mock.post.assert_called_once()
        self.assertEqual(r.status_code, 500)
        self.assertIn('CommerceHQ API Error', r.json().get('error'))

        # Without cache, calls api twice
        requests_mock.post = Mock(side_effect=[
            Mock(ok=True, json=Mock(return_value={
                'fulfilments': [{
                    'id': 1,
                    'items': [
                        {'id': track.line_id}
                    ]
                }]
            })),
            Mock(raise_for_status=Mock(return_value=None))
        ])

        quantity = 5
        caches['orders'].set(f'chq_quantity_{self.store.id}_{track.order_id}_{track.line_id}', quantity)

        r = self.client.post('/api/chq/fulfill-order', data)

        requests_mock.post.assert_has_calls([mock_call(
            url=self.store.get_api_url('orders', track.order_id, 'fulfilments'),
            json={'items': [{'id': track.line_id, 'quantity': quantity}]}
        )])
        self.assertEqual(r.status_code, 200)

        # Invalid fulfillment
        requests_mock.post = Mock(side_effect=[
            Mock(
                raise_for_status=Mock(side_effect=Exception()),
                text='fulfilment id is invalid'
            ),
            Mock(ok=True, json=Mock(return_value={
                'fulfilments': [{
                    'id': 10,
                    'items': [
                        {'id': track.line_id}
                    ]
                }]
            })),
            Mock(raise_for_status=Mock(return_value=None)),
        ])
        r = self.client.post('/api/chq/fulfill-order', data)

        self.assertEqual(r.status_code, 200)
        self.assertEqual(caches['orders'].get(f'chq_fulfilments_{self.store.id}_{track.order_id}_{track.line_id}'), 10)

        # Only query CHQ once
        requests_mock.post = Mock(raise_for_status=Mock(return_value=None))

        r = self.client.post('/api/chq/fulfill-order', data)
        self.assertEqual(r.status_code, 200)
        requests_mock.post.assert_called_once()

    @patch('commercehq_core.models.CommerceHQStore.request')
    def test_post_order_fulfill(self, requests_mock):
        track = CommerceHQOrderTrackFactory(user=self.user, store=self.store)

        fulfillment_id = 1
        requests_mock.post = Mock(return_value=Mock(
            json=Mock(return_value={
                'fulfilments': [{
                    'id': fulfillment_id,
                    'items': [
                        {'id': track.line_id}
                    ]
                }]
            }),
            raise_for_status=Mock(return_value=None)
        ))

        data = {
            'store': self.store.id,
            'order_id': track.order_id,
            'line_id': track.line_id,
            'line_sku': '',
            'aliexpress_order_id': '123',
            'source_type': 'aliexpress',
        }

        r = self.client.post('/api/chq/order-fulfill', data)
        self.assertEqual(r.status_code, 200)

        requests_mock.post.assert_called_once()
        cached_fulfillment_id = caches['orders'].get(f'chq_fulfilments_{self.store.id}_{track.order_id}_{track.line_id}')
        self.assertEqual(cached_fulfillment_id, fulfillment_id)

        # CommerceHQOrderTrack updated
        track.refresh_from_db()
        self.assertEqual(track.source_id, data['aliexpress_order_id'])
        self.assertEqual(track.source_type, data['source_type'])

        # Already fulfilled
        r = self.client.post('/api/chq/order-fulfill', {**data, 'aliexpress_order_id': '1'})

        self.assertEqual(r.status_code, 422)
        self.assertIn('already', r.json().get('error'))

    @patch('commercehq_core.models.CommerceHQProduct.sync', Mock(return_value=None))
    @patch('shopified_core.permissions.can_add_product')
    def test_post_import_product(self, can_add_product_mock):
        source_id = 12345678
        data = {
            'store': self.store.id,
            'product': source_id,
            'supplier': 'https://www.aliexpress.com/item/~/32961038442.html',
        }

        can_add_product_mock.return_value = [False, 1, 1]
        r = self.client.post('/api/chq/import-product', data)
        self.assertEqual(r.status_code, 401)
        can_add_product_mock.return_value = [True, 1, 1]

        r = self.client.post('/api/chq/import-product', data)
        self.assertEqual(r.status_code, 200)
        product = CommerceHQProduct.objects.get(id=r.json()['product'])
        self.assertEqual(product.source_id, source_id)
        self.assertTrue(product.have_supplier())

        r = self.client.post('/api/chq/import-product', data)
        self.assertEqual(r.status_code, 422)
        self.assertIn('connected', r.json().get('error'))

    def test_post_order_fulfill_update(self):
        track = CommerceHQOrderTrackFactory(user=self.user, store=self.store)
        data = {
            'store': self.store.id,
            'order': track.id,
            'source_id': '123',
            'tracking_number': '123',
            'status': 'PLACE_ORDER_SUCCESS',
            'end_reason': 'buyer_accept_goods',
            'order_details': json.dumps({})
        }

        r = self.client.post('/api/chq/order-fulfill-update', data)
        self.assertEqual(r.status_code, 200)
        track.refresh_from_db()
        self.assertEqual(track.source_tracking, data['tracking_number'])

        r = self.client.post('/api/chq/order-fulfill-update', {**data, 'bundle': {'source_id': '123'}})
        self.assertEqual(r.status_code, 200)
        track.refresh_from_db()
        track_data = json.loads(track.data)
        self.assertEqual(track_data['bundle']['123']['source_status'], data['status'])
        self.assertEqual(track_data['bundle']['123']['source_tracking'], data['tracking_number'])

    def test_delete_board_products(self):
        self.user.profile.plan.permissions.add(AppPermissionFactory(name='edit_product_boards.sub', description=''))
        board = CommerceHQBoardFactory(user=self.user)
        product = CommerceHQProductFactory(store=self.store, user=self.user)
        board.products.add(product)
        params = '?products[]={}&board_id={}'.format(product.id, board.id)
        r = self.client.delete('/api/chq/board-products' + params)
        self.assertEqual(r.status_code, 200)
        count = board.products.count()
        self.assertEqual(count, 0)

    def test_delete_board(self):
        self.user.profile.plan.permissions.add(AppPermissionFactory(name='edit_product_boards.sub', description=''))
        board = CommerceHQBoardFactory(user=self.user)
        params = '?board_id={}'.format(board.id)
        r = self.client.delete('/api/chq/board' + params)
        self.assertEqual(r.status_code, 200)
        count = self.user.commercehqboard_set.count()
        self.assertEqual(count, 0)

    def test_delete_product(self):
        self.user.profile.plan.permissions.add(AppPermissionFactory(name='delete_products.sub', description=''))
        product = CommerceHQProductFactory(store=self.store, user=self.user)
        params = '?product={}'.format(product.id)
        r = self.client.delete('/api/chq/product' + params)
        self.assertEqual(r.status_code, 200)
        count = self.user.commercehqproduct_set.count()
        self.assertEqual(count, 0)

    @patch('commercehq_core.api.unmonitor_store')
    def test_delete_store(self, unmonitor_store):
        self.assertEqual(self.store.is_active, True)
        params = '?store_id={}'.format(self.store.id)
        r = self.client.delete('/api/chq/store' + params)
        self.assertEqual(r.status_code, 200)
        self.store.refresh_from_db()
        self.assertEqual(self.store.is_active, False)
        unmonitor_store.assert_called_with(self.store)

    def test_delete_supplier(self):
        product = CommerceHQProductFactory(store=self.store, user=self.user, source_id=12345678)
        supplier1 = CommerceHQSupplierFactory(product=product)
        supplier2 = CommerceHQSupplierFactory(product=product)
        product.default_supplier = supplier1
        product.save()
        params = '?product={}&supplier={}'.format(product.id, supplier1.id)
        r = self.client.delete('/api/chq/supplier' + params)
        self.assertEqual(r.status_code, 200)
        count = product.commercehqsupplier_set.count()
        self.assertEqual(count, 1)
        product.refresh_from_db()
        self.assertEqual(product.default_supplier, supplier2)

    def test_post_supplier_default(self):
        product = CommerceHQProductFactory(store=self.store, user=self.user, source_id=12345678)
        supplier = CommerceHQSupplierFactory(product=product)
        data = {'product': product.id, 'export': supplier.id}
        r = self.client.post('/api/chq/supplier-default', data)
        self.assertEqual(r.status_code, 200)
        product.refresh_from_db()
        self.assertEqual(product.default_supplier, supplier)

    def test_post_supplier(self):
        product = CommerceHQProductFactory(store=self.store, user=self.user, source_id=12345678)
        data = {
            'product': product.id,
            'original-link': 'https://www.aliexpress.com/item/32213964945.html',
            'supplier-link': '123',
            'supplier-name': 'test'
        }
        r = self.client.post('/api/chq/supplier', data)
        self.assertEqual(r.status_code, 200)
        product.refresh_from_db()
        count = product.commercehqsupplier_set.count()
        self.assertEqual(count, 1)
        self.assertIsNotNone(product.default_supplier)

    @patch('commercehq_core.tasks.product_export.apply_async')
    def test_post_product_export(self, product_export):
        self.user.profile.plan.permissions.add(AppPermissionFactory(name='send_to_store.use', description=''))
        product = CommerceHQProductFactory(store=self.store, user=self.user, source_id=12345678)
        data = {
            'store': self.store.id,
            'product': product.id,
            'publish': 'true',
        }
        r = self.client.post('/api/chq/product-export', data)
        self.assertEqual(r.status_code, 200)
        args = [str(self.store.id), str(product.id), self.user.id, data['publish']]
        product_export.assert_called_with(args=args, countdown=0, expires=120)

    @patch('commercehq_core.tasks.product_save')
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
        r = self.client.post('/api/chq/product-save', data)
        self.assertEqual(r.status_code, 200)
        product_save.assert_called_once()

    @patch('commercehq_core.tasks.product_update.apply_async')
    def test_post_product_update(self, product_update):
        product = CommerceHQProductFactory(store=self.store, user=self.user, source_id=12345678)
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
        r = self.client.post('/api/chq/product-update', data)
        self.assertEqual(r.status_code, 200)
        product_update.assert_called_with(args=[product.id, product_data], countdown=0, expires=60)

    @tag('excessive')
    @patch('shopified_core.permissions.can_add_store', Mock(return_value=(True, 2, 0)))
    def test_post_store_add(self):
        data = {
            'title': 'Dropified Test App',
            'api_url': 'http://chq-shopified-test.commercehqtesting.com/admin',
            'api_key': 'gsycAdWxbv56CAQFNWVkN53sLxnzcSEF',
            'api_password': 'euld-IWsmA1SkT5dved51decAcrXoz6n'
        }
        r = self.client.post('/api/chq/store-add', data)
        self.assertEqual(r.status_code, 200)
        count = self.user.commercehqstore_set.count()
        self.assertEqual(count, 2)

    @patch('requests.sessions.Session.get')
    def test_get_store_verify(self, mock_get):
        r = self.client.get('/api/chq/store-verify', {'store': self.store.id})
        mock_get.assert_called_once()
        self.assertEqual(r.status_code, 200)

    def test_post_alert_archive(self):
        product = CommerceHQProductFactory(store=self.store, user=self.user, source_id=12345678)
        product_change1 = ProductChangeFactory(chq_product=product, user=self.user)
        product_change2 = ProductChangeFactory(chq_product=product, user=self.user)
        self.assertEqual(product_change1.hidden, False)
        self.assertEqual(product_change2.hidden, False)

        data = {
            'alert': product_change1.id,
        }
        r = self.client.post('/api/chq/alert-archive', data)
        self.assertEqual(r.status_code, 200)
        product_change1.refresh_from_db()
        product_change2.refresh_from_db()
        self.assertEqual(product_change1.hidden, True)
        self.assertEqual(product_change2.hidden, False)

        data = {
            'store': self.store.id,
            'all': 1,
        }
        r = self.client.post('/api/chq/alert-archive', data)
        self.assertEqual(r.status_code, 200)
        product_change2.refresh_from_db()
        self.assertEqual(product_change2.hidden, True)

    def test_post_alert_delete(self):
        product = CommerceHQProductFactory(store=self.store, user=self.user, source_id=12345678)
        ProductChangeFactory(chq_product=product, user=self.user)
        count = self.user.productchange_set.count()
        self.assertEqual(count, 1)

        data = {
            'store': self.store.id,
        }
        r = self.client.post('/api/chq/alert-delete', data)
        self.assertEqual(r.status_code, 200)
        count = self.user.productchange_set.count()
        self.assertEqual(count, 0)
