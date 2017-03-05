from django.test import TestCase
from django.core.urlresolvers import reverse

from leadgalaxy.tests.factories import UserFactory

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

    def test_must_return_correct_form_template(self):
        self.login()
        r = self.client.get(self.path)
        self.assertTemplateUsed(r, 'commercehq/index.html')

    def test_must_only_list_active_stores(self):
        CommerceHQStoreFactory(user=self.user, is_active=True)
        CommerceHQStoreFactory(user=self.user, is_active=False)
        self.login()
        r = self.client.get(self.path)
        self.assertEqual(r.context['stores'].count(), 1)

    def test_must_show_first_visit(self):
        self.login()
        r = self.client.get(self.path)
        self.assertTrue(r.context['first_visit'])

    def test_must_set_first_visit_to_false(self):
        self.login()
        r = self.client.get(self.path)
        self.user.profile.refresh_from_db()
        config = self.user.profile.get_config()
        self.assertFalse(config['_first_visit'])

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
            'api_url': 'https://example.commercehq.com',
            'api_key': 'testkey',
            'api_password': 'testpassword'}

        self.headers = {'HTTP_X_REQUESTED_WITH': 'XMLHttpRequest'}
        self.path = reverse('chq:store_create')

    def login(self):
        self.client.login(username=self.user.username, password=self.password)

    def test_must_require_requests_to_be_ajax(self):
        r = self.client.post(self.path, self.data)
        self.assertEqual(r.status_code, 404)

    def test_must_be_logged_in(self):
        r = self.client.post(self.path, self.data, **self.headers)
        self.assertEqual(r.status_code, 401)

    def test_must_create_new_store(self):
        self.login()
        r = self.client.post(self.path, self.data, **self.headers)
        self.assertEqual(r.status_code, 204)

    def test_must_add_store_to_user(self):
        self.login()
        r = self.client.post(self.path, self.data, **self.headers)
        store = CommerceHQStore.objects.get(api_url=self.data['api_url'])
        self.assertEqual(store.user, self.user)

    def test_must_not_allow_subusers_to_create(self):
        self.client.login(username=self.subuser.username, password=self.subuser_password)
        r = self.client.post(self.path, self.data, **self.headers)
        self.assertEqual(r.status_code, 403)


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
        self.assertTemplateUsed(r, 'commercehq/store_update_form.html')

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
        self.path = reverse('chq:board_create')
        self.data = {'title': 'Test Board'}
        self.headers = {'HTTP_X_REQUESTED_WITH': 'XMLHttpRequest'}

    def login(self):
        self.client.login(username=self.user.username, password=self.password)

    def test_must_require_requests_to_be_ajax(self):
        r = self.client.post(self.path, self.data)
        self.assertEqual(r.status_code, 404)

    def test_must_be_logged_in(self):
        r = self.client.post(self.path, self.data, **self.headers)
        self.assertEqual(r.status_code, 401)

    def test_must_create_new_board(self):
        self.login()
        r = self.client.post(self.path, self.data, **self.headers)
        self.assertEqual(r.status_code, 204)

    def test_must_add_board_to_user(self):
        self.login()
        r = self.client.post(self.path, self.data, **self.headers)
        board = CommerceHQBoard.objects.get(title=self.data['title'])
        self.assertEqual(board.user, self.user)

    def test_must_use_correct_template(self):
        self.login()
        r = self.client.post(self.path, {}, **self.headers)
        self.assertTemplateUsed(r, 'commercehq/board_create_form.html')


class BoardUpdateTestCase(TestCase):
    def setUp(self):
        self.user = UserFactory(username='test')
        self.password = 'test'
        self.user.set_password(self.password)
        self.user.save()
        self.board = CommerceHQBoardFactory(user=self.user)

        self.data = {'title': 'Test Board'}
        self.headers = {'HTTP_X_REQUESTED_WITH': 'XMLHttpRequest'}
        self.path = reverse('chq:board_update', args=(self.board.pk,))

    def login(self):
        self.client.login(username=self.user.username, password=self.password)

    def test_must_require_requests_to_be_ajax(self):
        r = self.client.get(self.path)
        self.assertEqual(r.status_code, 404)

    def test_must_be_logged_in(self):
        r = self.client.get(self.path, **self.headers)
        self.assertEqual(r.status_code, 401)

    def test_must_return_correct_form_template(self):
        self.login()
        r = self.client.get(self.path, **self.headers)
        self.assertTrue(r.status_code, 200)
        self.assertTemplateUsed(r, 'commercehq/board_update_form.html')

    def test_must_update_board(self):
        self.login()
        r = self.client.post(self.path, self.data, **self.headers)
        self.board.refresh_from_db()
        self.assertTrue(r.status_code, 204)
        self.assertTrue(self.board.title, self.data['title'])

    def test_must_not_return_other_user_board(self):
        board = CommerceHQBoardFactory()
        self.login()
        r = self.client.get(reverse('chq:board_update', args=(board.pk,)))
        self.assertEqual(r.status_code, 404)


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
