from django.test import TestCase
from django.core.urlresolvers import reverse

from leadgalaxy.tests.factories import UserFactory

from .factories import CommerceHQStoreFactory
from ..models import CommerceHQStore


class StoreCreateTestCase(TestCase):
    def setUp(self):
        self.user = UserFactory(username='test')
        self.password = 'test'
        self.user.set_password(self.password)
        self.user.save()
        self.data = {
            'title': 'Test Store',
            'api_url': 'https://example.commercehq.com',
            'api_key': 'testkey',
            'api_password': 'testpassword'}

    def test_must_be_logged_in(self):
        r = self.client.post(reverse('chq:store_create'), self.data)
        self.assertEquals(r.status_code, 302)

    def test_must_create_new_store(self):
        self.client.login(username=self.user.username, password=self.password)
        r = self.client.post(reverse('chq:store_create'), self.data)
        self.assertEquals(r.status_code, 201)

    def test_must_add_store_to_user(self):
        self.client.login(username=self.user.username, password=self.password)
        r = self.client.post(reverse('chq:store_create'), self.data)
        store = CommerceHQStore.objects.get(api_url=self.data['api_url'])
        self.assertEquals(store.user, self.user)


class StoreUpdateTestCase(TestCase):
    def setUp(self):
        self.user = UserFactory(username='test')
        self.password = 'test'
        self.user.set_password(self.password)
        self.user.save()
        self.store = CommerceHQStoreFactory(user=self.user)
        self.data = {
            'title': 'Test Store',
            'api_url': 'https://example.commercehq.com',
            'api_key': 'testkey',
            'api_password': 'testpassword'}

    def test_must_be_logged_in(self):
        r = self.client.get(reverse('chq:store_update', args=(self.store.pk,)))
        self.assertEquals(r.status_code, 302)

    def test_must_return_correct_form_template(self):
        self.client.login(username=self.user.username, password=self.password)
        r = self.client.get(reverse('chq:store_update', args=(self.store.pk,)))
        self.assertTrue(r.status_code, 200)
        self.assertTemplateUsed(r, 'commercehq/store_update_form.html')

    def test_must_update_store(self):
        self.client.login(username=self.user.username, password=self.password)
        r = self.client.post(reverse('chq:store_update', args=(self.store.pk,)), self.data)
        self.store.refresh_from_db()
        self.assertTrue(self.store.title, self.data['title'])


class StoreDeleteTestCase(TestCase):
    def setUp(self):
        self.user = UserFactory(username='test')
        self.password = 'test'
        self.user.set_password(self.password)
        self.user.save()
        self.store = CommerceHQStoreFactory(user=self.user)

    def test_must_be_logged_in(self):
        r = self.client.post(reverse('chq:store_delete', args=(self.store.pk,)))
        self.assertEquals(r.status_code, 302)

    def test_user_must_be_able_to_delete_own_store(self):
        self.client.login(username=self.user.username, password=self.password)
        r = self.client.post(reverse('chq:store_delete', args=(self.store.pk,)))
        count = self.user.commercehqstore_set.count()
        self.assertEquals(count, 0)

