from unittest.mock import patch
from lib.test import BaseTestCase, ProductAlertsBase
from django.urls import reverse

from leadgalaxy.tests.factories import (
    UserFactory,
)

from .factories import (
    GrooveKartProductFactory,
    GrooveKartStoreFactory,
    ProductChangeFactory,
    GrooveKartSupplierFactory,
)


class ProductAlertsTestCase(ProductAlertsBase):
    store_factory = GrooveKartStoreFactory
    product_factory = GrooveKartProductFactory
    supplier_factory = GrooveKartSupplierFactory
    change_factory = ProductChangeFactory

    def setUp(self):
        super().setUp()
        self.subuser.profile.subuser_gkart_stores.add(self.store)

        self.product_change1 = self.change_factory(
            gkart_product=self.product,
            user=self.user,
            store_type='gkart',
            data=self.change_data1,
        )

        self.product_change2 = self.change_factory(
            gkart_product=self.product,
            user=self.user,
            store_type='gkart',
            data=self.change_data2,
        )

    def test_subuser_can_access_alerts(self):
        self.subuser.profile.have_global_permissions()
        self.client.force_login(self.subuser)

        path = reverse('gkart:product_alerts')
        with patch('groovekart_core.utils.get_gkart_products',
                   return_value=[{'id': self.product.source_id}]):
            response = self.client.get(path)

        text = response.content.decode()
        key = 'Is now <b style="color:green">Online</b>'

        self.assertEqual(text.count(key), 2)


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
