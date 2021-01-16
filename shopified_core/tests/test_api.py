from unittest.mock import patch

from lib.test import BaseTestCase

from leadgalaxy.tests import factories as f


class ApiBaseTestCase(BaseTestCase):
    def setUp(self):
        self.parent_user = f.UserFactory()
        self.user = f.UserFactory()
        self.password = 'test'
        self.user.set_password(self.password)
        self.user.save()

        self.store = f.ShopifyStoreFactory(user=self.user)
        self.client.login(username=self.user.username, password=self.password)

    def test_post_add_extra_store(self):
        self.assertEqual(self.store.extra.count(), 0)

        data = {
            'store_id': self.store.id,
            'store_type': 'shopify',
        }

        with patch('leadgalaxy.models.GroupPlan.is_stripe',
                   return_value=True):
            r = self.client.post('/api/add-extra-store', data)
            self.assertEqual(r.status_code, 200)
            self.assertEqual(self.store.extra.count(), 1)

    def test_post_can_not_add_extra_store(self):
        self.assertEqual(self.store.extra.count(), 0)

        data = {
            'store_id': self.store.id,
            'store_type': 'shopify',
        }

        r = self.client.post('/api/add-extra-store', data)
        self.assertEqual(r.status_code, 403)
        self.assertEqual(self.store.extra.count(), 0)
