from unittest.mock import patch

from lib.test import BaseTestCase

from .factories import GearBubbleStoreFactory, GearBubbleProductFactory

from leadgalaxy.models import SUBUSER_GEAR_STORE_PERMISSIONS
from leadgalaxy.tests.factories import UserFactory


class GearBubbleStoreTestCase(BaseTestCase):
    def test_must_have_subuser_permissions(self):
        store = GearBubbleStoreFactory()
        self.assertEqual(store.subuser_gear_permissions.count(), len(SUBUSER_GEAR_STORE_PERMISSIONS))

    def test_must_add_subuser_permissions_on_create_only(self):
        store = GearBubbleStoreFactory()
        store.title = 'Updated title'
        store.save()
        self.assertEqual(store.subuser_gear_permissions.count(), len(SUBUSER_GEAR_STORE_PERMISSIONS))


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


class GearBubbleProductTestCase(BaseTestCase):
    def setUp(self):
        self.product = GearBubbleProductFactory()

    @patch('django.conf.settings.DEBUG', False)
    @patch('django.conf.settings.KEEN_PROJECT_ID', True)
    @patch('keen.add_event')
    def test_send_keen_event_on_create(self, keen_add_event):
        product = GearBubbleProductFactory()
        keen_add_event.assert_called_with(
            'product_created',
            {
                'keen': {
                    'addons': [{
                        'name': 'keen:url_parser',
                        'input': {'url': 'source_url'},
                        'output': 'parsed_source_url'
                    }]
                },
                'source_url': None,
                'store': product.store.title,
                'store_type': 'GearBubble',
                'product_title': product.title,
                'product_price': product.price,
                'product_type': product.product_type,
            }
        )

    @patch('django.conf.settings.DEBUG', False)
    @patch('django.conf.settings.KEEN_PROJECT_ID', True)
    @patch('keen.add_event')
    def test_not_send_keen_event_on_update(self, keen_add_event):
        self.product.save()
        keen_add_event.assert_not_called()
