from lib.test import BaseTestCase

from .factories import GearBubbleStoreFactory

from leadgalaxy.models import SUBUSER_GEAR_STORE_PERMISSIONS
from leadgalaxy.tests.factories import UserFactory

from analytic_events.models import StoreCreatedEvent


class GearBubbleStoreTestCase(BaseTestCase):
    def test_must_have_subuser_permissions(self):
        store = GearBubbleStoreFactory()
        self.assertEqual(store.subuser_gear_permissions.count(), len(SUBUSER_GEAR_STORE_PERMISSIONS))

    def test_must_add_subuser_permissions_on_create_only(self):
        store = GearBubbleStoreFactory()
        store.title = 'Updated title'
        store.save()
        self.assertEqual(store.subuser_gear_permissions.count(), len(SUBUSER_GEAR_STORE_PERMISSIONS))

    def test_must_create_store_created_event_when_created(self):
        GearBubbleStoreFactory()
        self.assertEqual(StoreCreatedEvent.objects.count(), 1)

    def test_must_not_create_store_created_event_when_saved(self):
        store = GearBubbleStoreFactory()
        StoreCreatedEvent.objects.all().delete()
        store.title = 'new'
        store.save()
        self.assertEqual(StoreCreatedEvent.objects.count(), 0)


class UserProfileTestCase(BaseTestCase):
    def test_subusers_must_have_all_store_permissions_when_assigned_a_store(self):
        parent_user = UserFactory()
        store = GearBubbleStoreFactory(user=parent_user)
        user = UserFactory()
        user.profile.subuser_parent = parent_user
        user.profile.save()
        user.profile.subuser_gear_stores.add(store)
        store_permissions_count = user.profile.subuser_gear_permissions.filter(store=store).count()
        self.assertEqual(store_permissions_count, len(SUBUSER_GEAR_STORE_PERMISSIONS))
