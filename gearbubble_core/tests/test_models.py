from django.test import TestCase

from .factories import GearBubbleStoreFactory

from leadgalaxy.models import SUBUSER_GEAR_STORE_PERMISSIONS
from leadgalaxy.tests.factories import UserFactory


class GearBubbleStoreTestCase(TestCase):
    def test_must_have_subuser_permissions(self):
        store = GearBubbleStoreFactory()
        self.assertEqual(store.subuser_gear_permissions.count(), len(SUBUSER_GEAR_STORE_PERMISSIONS))

    def test_must_add_subuser_permissions_on_create_only(self):
        store = GearBubbleStoreFactory()
        store.title = 'Updated title'
        store.save()
        self.assertEqual(store.subuser_gear_permissions.count(), len(SUBUSER_GEAR_STORE_PERMISSIONS))


class UserProfileTestCase(TestCase):
    def test_subusers_must_have_all_store_permissions_when_assigned_a_store(self):
        parent_user = UserFactory()
        store = GearBubbleStoreFactory(user=parent_user)
        user = UserFactory()
        user.profile.subuser_parent = parent_user
        user.profile.save()
        user.profile.subuser_gear_stores.add(store)
        store_permissions_count = user.profile.subuser_gear_permissions.filter(store=store).count()
        self.assertEqual(store_permissions_count, len(SUBUSER_GEAR_STORE_PERMISSIONS))
