from lib.test import BaseTestCase

from leadgalaxy.tests.factories import (
    UserFactory,
)

from .factories import (
    GrooveKartProductFactory,
    GrooveKartStoreFactory,
    ProductChangeFactory,
)


class ApiTestCase(BaseTestCase):
    def setUp(self):
        self.parent_user = UserFactory()
        self.user = UserFactory()
        self.password = 'test'
        self.user.set_password(self.password)
        self.user.save()

        self.store = GrooveKartStoreFactory(user=self.user)
        self.client.login(username=self.user.username, password=self.password)

    def test_post_alert_archive(self):
        product = GrooveKartProductFactory(store=self.store, user=self.user, source_id=12345678)
        product_change1 = ProductChangeFactory(gkart_product=product, user=self.user)
        product_change2 = ProductChangeFactory(gkart_product=product, user=self.user)
        self.assertEqual(product_change1.hidden, False)
        self.assertEqual(product_change2.hidden, False)

        data = {
            'alert': product_change1.id,
        }
        r = self.client.post('/api/gkart/alert-archive', data)
        self.assertEqual(r.status_code, 200)
        product_change1.refresh_from_db()
        product_change2.refresh_from_db()
        self.assertEqual(product_change1.hidden, True)
        self.assertEqual(product_change2.hidden, False)

        data = {
            'store': self.store.id,
            'all': 1,
        }
        r = self.client.post('/api/gkart/alert-archive', data)
        self.assertEqual(r.status_code, 200)
        product_change2.refresh_from_db()
        self.assertEqual(product_change2.hidden, True)

    def test_post_alert_delete(self):
        product = GrooveKartProductFactory(store=self.store, user=self.user, source_id=12345678)
        ProductChangeFactory(gkart_product=product, user=self.user)
        count = self.user.productchange_set.count()
        self.assertEqual(count, 1)

        data = {
            'store': self.store.id,
        }
        r = self.client.post('/api/gkart/alert-delete', data)
        self.assertEqual(r.status_code, 200)
        count = self.user.productchange_set.count()
        self.assertEqual(count, 0)
