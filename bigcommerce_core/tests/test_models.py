from lib.test import BaseTestCase

from .factories import BigCommerceStoreFactory

from leadgalaxy.models import SUBUSER_BIGCOMMERCE_STORE_PERMISSIONS
from leadgalaxy.tests.factories import UserFactory


class BigCommerceStoreTestCase(BaseTestCase):
    def test_must_have_subuser_permissions(self):
        store = BigCommerceStoreFactory()
        self.assertEqual(store.subuser_bigcommerce_permissions.count(), len(SUBUSER_BIGCOMMERCE_STORE_PERMISSIONS))

    def test_must_add_subuser_permissions_on_create_only(self):
        store = BigCommerceStoreFactory()
        store.title = 'Updated title'
        store.save()
        self.assertEqual(store.subuser_bigcommerce_permissions.count(), len(SUBUSER_BIGCOMMERCE_STORE_PERMISSIONS))


class UserProfileTestCase(BaseTestCase):
    def test_subusers_must_have_all_store_permissions_when_assigned_a_store(self):
        parent_user = UserFactory()
        store = BigCommerceStoreFactory(user=parent_user)
        user = UserFactory()
        user.profile.subuser_parent = parent_user
        user.profile.save()
        user.profile.subuser_bigcommerce_stores.add(store)
        store_permissions_count = user.profile.subuser_bigcommerce_permissions.filter(store=store).count()
        self.assertEqual(store_permissions_count, len(SUBUSER_BIGCOMMERCE_STORE_PERMISSIONS))
