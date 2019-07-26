from unittest.mock import Mock, patch, PropertyMock

from lib.test import BaseTestCase

from .factories import WooStoreFactory, WooProductFactory

from leadgalaxy.models import SUBUSER_WOO_STORE_PERMISSIONS
from leadgalaxy.tests.factories import UserFactory


class WooStoreFactoryTestCase(BaseTestCase):
    def test_must_have_subuser_permissions(self):
        store = WooStoreFactory()
        self.assertEqual(store.subuser_woo_permissions.count(), len(SUBUSER_WOO_STORE_PERMISSIONS))

    def test_must_add_subuser_permissions_on_create_only(self):
        store = WooStoreFactory()
        store.title = 'Updated title'
        store.save()
        self.assertEqual(store.subuser_woo_permissions.count(), len(SUBUSER_WOO_STORE_PERMISSIONS))


class UserProfileTestCase(BaseTestCase):
    def test_subusers_must_have_all_store_permissions_when_assigned_a_store(self):
        parent_user = UserFactory()
        store = WooStoreFactory(user=parent_user)
        user = UserFactory()
        user.profile.subuser_parent = parent_user
        user.profile.save()
        user.profile.subuser_woo_stores.add(store)
        store_permissions_count = user.profile.subuser_woo_permissions.filter(store=store).count()
        self.assertEqual(store_permissions_count, len(SUBUSER_WOO_STORE_PERMISSIONS))


class WooProductTestCase(BaseTestCase):
    def test_must_use_the_weight_unit_value_returned_by_woocommerce(self):
        with patch('woocommerce_core.models.WooStore.wcapi', new_callable=PropertyMock) as wcapi:
            product = WooProductFactory(source_id=1)
            product.update_data({'weight_unit': 'lbs'})
            product.save()
            r = Mock()
            r.raise_for_status = Mock(return_value=None)
            r.json = Mock(return_value={'value': 'g'})
            request = Mock()
            request.get = Mock(return_value=r)
            wcapi.return_value = request
            product.update_weight_unit()
            new_weight_unit = product.parsed.get('weight_unit')
            self.assertEqual(new_weight_unit, 'g')
