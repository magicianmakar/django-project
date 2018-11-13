from lib.test import BaseTestCase

from .factories import CommerceHQStoreFactory

from leadgalaxy.models import SUBUSER_CHQ_STORE_PERMISSIONS
from leadgalaxy.tests.factories import UserFactory


class CommerceHQStoreFactoryTestCase(BaseTestCase):
    def test_must_have_subuser_permissions(self):
        store = CommerceHQStoreFactory()
        self.assertEqual(store.subuser_chq_permissions.count(), len(SUBUSER_CHQ_STORE_PERMISSIONS))

    def test_must_add_subuser_permissions_on_create_only(self):
        store = CommerceHQStoreFactory()
        store.title = 'Updated title'
        store.save()
        self.assertEqual(store.subuser_chq_permissions.count(), len(SUBUSER_CHQ_STORE_PERMISSIONS))


class UserProfileTestCase(BaseTestCase):
    def test_subusers_must_have_all_store_permissions_when_assigned_a_store(self):
        parent_user = UserFactory()
        store = CommerceHQStoreFactory(user=parent_user)
        user = UserFactory()
        user.profile.subuser_parent = parent_user
        user.profile.save()
        user.profile.subuser_chq_stores.add(store)
        store_permissions_count = user.profile.subuser_chq_permissions.filter(store=store).count()
        self.assertEqual(store_permissions_count, len(SUBUSER_CHQ_STORE_PERMISSIONS))
