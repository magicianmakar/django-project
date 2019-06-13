from unittest.mock import patch

from lib.test import BaseTestCase

from .factories import GrooveKartStoreFactory, GrooveKartProductFactory

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


class GrooveKartProductTestCase(BaseTestCase):
    def setUp(self):
        self.product = GrooveKartProductFactory()

    @patch('django.conf.settings.DEBUG', False)
    @patch('django.conf.settings.KEEN_PROJECT_ID', True)
    @patch('shopified_core.tasks.keen_send_event.delay')
    def test_send_keen_event_on_create(self, keen_add_event):
        product = GrooveKartProductFactory()
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
                'store_type': 'GrooveKart',
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
