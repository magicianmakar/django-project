from django.test import TestCase

from .factories import WooStoreFactory

from leadgalaxy.models import SUBUSER_WOO_STORE_PERMISSIONS
from leadgalaxy.tests.factories import UserFactory


class WooStoreFactoryTestCase(TestCase):
    def test_must_have_subuser_permissions(self):
        store = WooStoreFactory()
        self.assertEqual(store.subuser_woo_permissions.count(), len(SUBUSER_WOO_STORE_PERMISSIONS))

    def test_must_add_subuser_permissions_on_create_only(self):
        store = WooStoreFactory()
        store.title = 'Updated title'
        store.save()
        self.assertEqual(store.subuser_woo_permissions.count(), len(SUBUSER_WOO_STORE_PERMISSIONS))


class UserProfileTestCase(TestCase):
    def test_subusers_must_have_all_store_permissions_when_assigned_a_store(self):
        parent_user = UserFactory()
        store = WooStoreFactory(user=parent_user)
        user = UserFactory()
        user.profile.subuser_parent = parent_user
        user.profile.save()
        user.profile.subuser_woo_stores.add(store)
        store_permissions_count = user.profile.subuser_woo_permissions.filter(store=store).count()
        self.assertEqual(store_permissions_count, len(SUBUSER_WOO_STORE_PERMISSIONS))
