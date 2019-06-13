from unittest.mock import patch

from lib.test import BaseTestCase

from .factories import CommerceHQStoreFactory, CommerceHQProductFactory

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


class CommerceHQProductTestCase(BaseTestCase):
    def setUp(self):
        self.product = CommerceHQProductFactory()

    @patch('django.conf.settings.DEBUG', False)
    @patch('django.conf.settings.KEEN_PROJECT_ID', True)
    @patch('shopified_core.tasks.keen_send_event.delay')
    def test_send_keen_event_on_create(self, keen_add_event):
        product = CommerceHQProductFactory()
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
                'store_type': 'CommerceHQ',
                'product_title': product.title,
                'product_price': product.price,
                'product_type': product.product_type,
            }
        )

    @patch('django.conf.settings.DEBUG', False)
    @patch('django.conf.settings.KEEN_PROJECT_ID', True)
    @patch('shopified_core.tasks.keen_send_event.delay')
    def test_not_send_keen_event_on_update(self, keen_add_event):
        self.product.save()
        keen_add_event.assert_not_called()
