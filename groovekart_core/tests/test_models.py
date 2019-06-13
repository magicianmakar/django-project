from lib.test import BaseTestCase

from .factories import GrooveKartStoreFactory

from leadgalaxy.models import SUBUSER_GKART_STORE_PERMISSIONS
from leadgalaxy.tests.factories import UserFactory


class GrooveKartStoreTestCase(BaseTestCase):
    def test_must_have_subuser_permissions(self):
        store = GrooveKartStoreFactory()
        self.assertEqual(store.subuser_gkart_permissions.count(), len(SUBUSER_GKART_STORE_PERMISSIONS))

    def test_must_add_subuser_permissions_on_create_only(self):
        store = GrooveKartStoreFactory()
        store.title = 'Updated title'
        store.save()
        self.assertEqual(store.subuser_gkart_permissions.count(), len(SUBUSER_GKART_STORE_PERMISSIONS))


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
