import json

from mock import patch, Mock

from django.test import TestCase
from django.core.urlresolvers import reverse

from leadgalaxy.tests.factories import UserFactory, GroupPlanFactory, AppPermissionFactory

from ..models import GearBubbleStore

from .factories import GearBubbleStoreFactory


class StoreListTestCase(TestCase):
    def setUp(self):
        self.user = UserFactory(username='test')
        self.password = 'test'
        self.user.set_password(self.password)
        self.user.save()

        self.user.profile.plan = GroupPlanFactory()
        permission = AppPermissionFactory(name='gearbubble.use')
        self.user.profile.plan.permissions.add(permission)
        self.user.profile.save()

        self.path = reverse('gear:index')

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
        self.assertTemplateUsed(r, 'gearbubble/index.html')

    def test_must_only_list_active_stores(self):
        GearBubbleStoreFactory(user=self.user, is_active=True)
        GearBubbleStoreFactory(user=self.user, is_active=False)
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

        self.data = {'title': 'Test Store', 'api_token': 'https://gearstore.com'}

        self.headers = {'HTTP_X_REQUESTED_WITH': 'XMLHttpRequest'}
        self.path = '/api/gear/store-add'

    def login(self):
        self.client.login(username=self.user.username, password=self.password)

    @patch('shopified_core.permissions.user_can_add', Mock(return_value=None))
    @patch('shopified_core.permissions.can_add_store', Mock(return_value=(True, 2, 0)))
    def test_must_add_store_to_user(self):
        self.login()
        r = self.client.post(self.path, self.data, **self.headers)

        store = GearBubbleStore.objects.first()

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
        self.path = '/api/gear/store'

    def login(self):
        self.client.login(username=self.user.username, password=self.password)

    def test_store_id_is_required(self):
        self.login()
        r = self.client.get(self.path, **self.headers)
        self.assertEqual(r.status_code, 400)

    @patch('shopified_core.permissions.user_can_view', Mock(return_value=None))
    def test_user_must_be_able_to_get_own_store(self):
        self.login()
        store = GearBubbleStoreFactory(user=self.user)
        r = self.client.get(self.path, {'id': store.id}, **self.headers)
        data = json.loads(r.content)
        self.assertEqual(data['id'], store.id)

    @patch('shopified_core.permissions.user_can_view', Mock(return_value=None))
    def test_user_must_not_be_able_to_get_not_owned_store(self):
        self.login()
        store = GearBubbleStoreFactory()
        r = self.client.get(self.path, {'id': store.id}, **self.headers)
        self.assertEqual(r.status_code, 404)

    @patch('shopified_core.permissions.user_can_view', Mock(return_value=None))
    def test_subuser_must_be_able_to_get_models_user_store(self):
        self.client.login(username=self.subuser.username, password=self.subuser_password)
        store = GearBubbleStoreFactory(user=self.subuser.models_user)
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

        self.data = {'title': 'Test Store', 'api_token': 'https://gearstore.com'}

        self.store = GearBubbleStoreFactory(user=self.user, **self.data)

        self.headers = {'HTTP_X_REQUESTED_WITH': 'XMLHttpRequest'}
        self.path = '/api/gear/store-update'

    def login(self):
        self.client.login(username=self.user.username, password=self.password)

    def test_store_id_is_required(self):
        self.login()
        r = self.client.post(self.path, {'title': 'New Title'}, **self.headers)
        self.assertEqual(r.status_code, 400)

    @patch('shopified_core.permissions.user_can_edit', Mock(return_value=None))
    def test_user_must_be_able_to_update(self):
        self.login()
        data = {'id': self.store.id, 'title': 'New Title', 'api_token': 'https://newgearstore.com'}

        r = self.client.post(self.path, data, **self.headers)
        self.store.refresh_from_db()

        self.assertEqual(self.store.title, data['title'])
        self.assertEqual(self.store.api_token, data['api_token'])
        self.assertEqual(r.reason_phrase, 'OK')

    def test_must_not_allow_subusers_to_update(self):
        self.client.login(username=self.subuser.username, password=self.subuser_password)
        data = {'id': self.store.id, 'title': 'New Title', 'api_token': 'https://newgearstore.com'}

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

        self.store = GearBubbleStoreFactory(user=self.user)
        self.headers = {'HTTP_X_REQUESTED_WITH': 'XMLHttpRequest'}
        self.path = '/api/gear/store?id=%s' % self.store.pk

    def test_must_be_logged_in(self):
        r = self.client.delete(self.path, **self.headers)
        self.assertEqual(r.status_code, 401)

    def test_store_id_is_required(self):
        self.client.login(username=self.user.username, password=self.password)
        r = self.client.delete('/api/gear/store', **self.headers)
        self.assertEqual(r.status_code, 400)

    def test_user_must_be_able_to_delete_own_store(self):
        self.client.login(username=self.user.username, password=self.password)
        r = self.client.delete(self.path, **self.headers)
        count = self.user.gearbubblestore_set.filter(is_active=True).count()
        self.assertTrue(r.reason_phrase, 'OK')
        self.assertEqual(count, 0)

    def test_must_not_allow_subusers_to_delete(self):
        self.client.login(username=self.subuser.username, password=self.subuser_password)
        r = self.client.delete(self.path, **self.headers)
        self.assertEqual(r.status_code, 403)
