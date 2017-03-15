import json

from mock import patch, Mock

from django.test import TestCase
from django.core.urlresolvers import reverse

from leadgalaxy.tests.factories import UserFactory, GroupPlanFactory, AppPermissionFactory

from .factories import (
    CommerceHQStoreFactory,
    CommerceHQBoardFactory,
    CommerceHQProductFactory,
)
from ..models import CommerceHQStore, CommerceHQBoard


class StoreListTestCase(TestCase):
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
            'api_url': 'https://chq-shopified-dev.commercehqdev.com/admin',
            'api_key': 'uVlgBcvwRtP2GvIkp6HbxDNA-PJ9c3Z7',
            'api_password': '7zg_g6yr1L4SEY50X2Ur_J57G0O6RhyM'}

        self.headers = {'HTTP_X_REQUESTED_WITH': 'XMLHttpRequest'}
        self.path = '/api/chq/store-add'

    def login(self):
        self.client.login(username=self.user.username, password=self.password)

    @patch('shopified_core.permissions.can_add_store', Mock(return_value=(True, 2, 0)))
    def test_must_create_new_store(self):
        self.login()
        r = self.client.post(self.path, self.data, **self.headers)
        self.assertEqual(r.reason_phrase, 'OK')

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

        self.data['api_url'] = 'https://chq-shopified-dev.commerce.com/admin'

        r = self.client.post(self.path, self.data, **self.headers)
        rep = json.loads(r.content)

        self.assertIn('stores URL is not correct', rep.get('error'))
        self.assertNotEqual(r.reason_phrase, 'OK')

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


class StoreUpdateTestCase(TestCase):
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

        self.store = CommerceHQStoreFactory(user=self.user)
        self.headers = {'HTTP_X_REQUESTED_WITH': 'XMLHttpRequest'}
        self.path = '/api/chq/store?store_id=%s' % self.store.pk

    def test_must_be_logged_in(self):
        r = self.client.delete(self.path, **self.headers)
        self.assertEqual(r.status_code, 401)

    def test_user_must_be_able_to_delete_own_store(self):
        self.client.login(username=self.user.username, password=self.password)
        r = self.client.delete(self.path, **self.headers)
        count = self.user.commercehqstore_set.filter(is_active=True).count()
        self.assertEqual(count, 0)

    def test_must_not_allow_subusers_to_delete(self):
        self.client.login(username=self.subuser.username, password=self.subuser_password)
        r = self.client.delete(self.path, **self.headers)
        self.assertEqual(r.status_code, 403)


class BoardsListTestCase(TestCase):
    def setUp(self):
        self.user = UserFactory(username='test')
        self.password = 'test'
        self.user.set_password(self.password)
        self.user.save()
        self.path = reverse('chq:boards_list')

    def login(self):
        self.client.login(username=self.user.username, password=self.password)

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


class BoardCreateTestCase(TestCase):
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
        r = self.client.post(self.path, self.data, **self.headers)
        board = CommerceHQBoard.objects.get(title=self.data['title'])
        self.assertEqual(board.user, self.user)

    @patch('commercehq_core.api.permissions.can_add_board', Mock(return_value=(True, True, True)))
    def test_board_name_is_required(self):
        self.login()
        r = self.client.post(self.path, {'title': ''}, **self.headers)
        self.assertEqual(r.status_code, 501)


class BoardUpdateTestCase(TestCase):
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


class BoardDeleteTestCase(TestCase):
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


class BoardEmptyTestCase(TestCase):
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
        r = self.client.post(self.path, data={'board_id': self.board.pk}, **self.headers)
        count = self.board.products.count()
        self.assertEqual(count, 0)


class BoardDetailTestCase(TestCase):
    def setUp(self):
        self.user = UserFactory(username='test')
        self.password = 'test'
        self.user.set_password(self.password)
        self.user.save()
        self.board = CommerceHQBoardFactory(user=self.user, title='Test Board')
        self.board2 = CommerceHQBoardFactory(title='Test Board2')
        self.path = reverse('chq:board_detail', args=(self.board.pk,))

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
