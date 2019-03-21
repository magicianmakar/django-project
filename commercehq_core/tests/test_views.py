import json
from unittest.mock import patch, Mock


from lib.test import BaseTestCase
from django.urls import reverse
from django.test import tag

from leadgalaxy.tests.factories import UserFactory, GroupPlanFactory, AppPermissionFactory
from leadgalaxy.models import SubuserPermission

from .factories import (
    CommerceHQStoreFactory,
    CommerceHQBoardFactory,
    CommerceHQProductFactory,
)
from ..models import CommerceHQStore, CommerceHQBoard


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

        self.path = reverse('chq:index')

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
        self.assertTemplateUsed(r, 'commercehq/index.html')

    def test_must_only_list_active_stores(self):
        CommerceHQStoreFactory(user=self.user, is_active=True)
        CommerceHQStoreFactory(user=self.user, is_active=False)
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
            'title': 'Dropified Test App',
            'api_url': 'http://chq-shopified-test.commercehqtesting.com/admin',
            'api_key': 'gsycAdWxbv56CAQFNWVkN53sLxnzcSEF',
            'api_password': 'euld-IWsmA1SkT5dved51decAcrXoz6n'}

        self.headers = {'HTTP_X_REQUESTED_WITH': 'XMLHttpRequest'}
        self.path = '/api/chq/store-add'

    def login(self):
        self.client.login(username=self.user.username, password=self.password)

    @tag('slow')
    @patch('shopified_core.permissions.can_add_store', Mock(return_value=(True, 2, 0)))
    def test_must_create_new_store(self):
        self.login()
        r = self.client.post(self.path, self.data, **self.headers)
        self.assertEqual(r.reason_phrase, 'OK')

    @tag('slow')
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

        self.assertIn('API credetnails is not correct', rep.get('error'))
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


class SubuserpermissionsApiTestCase(BaseTestCase):
    def setUp(self):
        self.error_message = "Permission Denied: You don't have permission to perform this action"
        self.parent_user = UserFactory()
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
    def test_subuser_can_save_for_later_with_permission(self):
        self.user.profile.subuser_chq_stores.add(self.store)
        data = {'store': self.store.id}
        r = self.client.post('/api/chq/save-for-later', data, **self.headers)
        self.assertEqual(r.status_code, 200)

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
