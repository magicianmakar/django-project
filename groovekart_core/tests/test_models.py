from unittest.mock import patch

from lib.test import BaseTestCase

from .factories import GrooveKartStoreFactory

from leadgalaxy.models import SUBUSER_GKART_STORE_PERMISSIONS
from leadgalaxy.tests.factories import UserFactory

from analytic_events.models import StoreCreatedEvent


class GrooveKartStoreTestCase(BaseTestCase):
    def test_must_have_subuser_permissions(self):
        store = GrooveKartStoreFactory()
        self.assertEqual(store.subuser_gkart_permissions.count(), len(SUBUSER_GKART_STORE_PERMISSIONS))

    def test_must_add_subuser_permissions_on_create_only(self):
        store = GrooveKartStoreFactory()
        store.title = 'Updated title'
        store.save()
        self.assertEqual(store.subuser_gkart_permissions.count(), len(SUBUSER_GKART_STORE_PERMISSIONS))

    def test_must_create_store_created_event_when_created(self):
        GrooveKartStoreFactory()
        self.assertEqual(StoreCreatedEvent.objects.count(), 1)
        print(StoreCreatedEvent.objects.first().churnzero_script)

    def test_must_not_create_store_created_event_when_saved(self):
        store = GrooveKartStoreFactory()
        StoreCreatedEvent.objects.all().delete()
        store.title = 'new'
        store.save()
        self.assertEqual(StoreCreatedEvent.objects.count(), 0)


class UserProfileTestCase(BaseTestCase):
    def test_subusers_must_have_all_store_permissions_when_assigned_a_store(self):
        parent_user = UserFactory()
        store = GrooveKartStoreFactory(user=parent_user)
        user = UserFactory()
        user.profile.subuser_parent = parent_user
        user.profile.save()
        user.profile.subuser_gkart_stores.add(store)
        store_permissions_count = user.profile.subuser_gkart_permissions.filter(store=store).count()
        self.assertEqual(store_permissions_count, len(SUBUSER_GKART_STORE_PERMISSIONS))


class GrooveKartStoreSessionTestCase(BaseTestCase):
    @patch('groovekart_core.models.Session.post')
    def test_must_call_with_credentials(self, post_request):
        store = GrooveKartStoreFactory(api_token='token', api_key='key')
        store.request.post('test', json={'test': 'example'})
        data = {'test': 'example', 'auth_token': 'token', 'api_key': 'key', 'api_user': 'dropified'}
        post_request.assert_called_with('test', json=data)
