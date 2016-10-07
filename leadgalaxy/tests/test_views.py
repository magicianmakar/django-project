import json

from django.test import TestCase
from django.core.urlresolvers import reverse
from django.core.cache import cache

from mock import patch, Mock

import factories as f

from stripe_subscription.tests.factories import StripeCustomerFactory
from stripe_subscription.models import StripeCustomer

from leadgalaxy.views import get_product

class ProfileViewTestCase(TestCase):
    def setUp(self):
        self.user = f.UserFactory(username='test')
        self.password = 'test'
        self.user.set_password(self.password)
        self.user.save()
        StripeCustomerFactory(user=self.user)

    @patch.object(StripeCustomer, 'source', None)
    @patch.object(StripeCustomer, 'get_invoices')
    def test_get_invoices_is_not_called_on_initial_load(self, get_invoices):
        self.client.login(username=self.user.username, password=self.password)
        response = self.client.get(reverse('user_profile'))
        self.assertEquals(response.status_code, 200)
        self.assertFalse(get_invoices.called)


class ProfileInvoicesTestCase(TestCase):
    def setUp(self):
        self.user = f.UserFactory(username='test')
        self.password = 'test'
        self.user.set_password(self.password)
        self.user.save()
        StripeCustomerFactory(user=self.user)

    def tearDown(self):
        cache.clear()
        cache.close()

    @patch.object(StripeCustomer, 'get_invoices')
    def test_get_invoices_is_called_once_because_of_caching(self, get_invoices):
        get_invoices.return_value = []
        self.client.login(username=self.user.username, password=self.password)
        kwargs = {'HTTP_X_REQUESTED_WITH': 'XMLHttpRequest'}
        self.client.get(reverse('user_profile_invoices'), **kwargs)
        self.client.get(reverse('user_profile_invoices'), **kwargs)
        self.assertEquals(get_invoices.call_count, 1)


class GetProductTestCase(TestCase):
    def setUp(self):
        self.user = f.UserFactory(username='test')
        self.password = 'test'
        self.user.set_password(self.password)
        self.user.profile.delete()
        self.user.save()
        self.store = f.ShopifyStoreFactory()
        self.store.user = self.user
        self.store.save()
        f.UserProfileFactory(user=self.user)
        self.client.login(username=self.user.username, password=self.password)

    def test_products_can_be_filtered_by_title(self):
        product = f.ShopifyProductFactory(
            user=self.user,
            store=self.store,
            data=json.dumps({'title': 'this is a test'})
        )
        f.ShopifyProductFactory(
            user=self.user,
            store=self.store,
            data=json.dumps({'title': 'not retrieved'})
        )
        request = Mock()
        request.user = self.user
        request.GET = {'title': 'test'}
        items = get_product(request, filter_products=True)[0]
        products = [item['qelem'] for item in items]
        self.assertIn(product, products)
        self.assertEquals(len(products), 1)

    def test_products_can_be_sorted_by_title(self):
        product1 = f.ShopifyProductFactory(
            user=self.user,
            store=self.store,
            data=json.dumps({'title': 'this is a test A'})
        )
        product2 = f.ShopifyProductFactory(
            user=self.user,
            store=self.store,
            data=json.dumps({'title': 'this is a test B'})
        )
        product3 = f.ShopifyProductFactory(
            user=self.user,
            store=self.store,
            data=json.dumps({'title': 'this is a test C'})
        )
        request = Mock()
        request.user = self.user
        request.GET = {}
        items = get_product(request, False, sort='-title')[0]
        products = [item['qelem'] for item in items]
        self.assertEquals([product3, product2, product1], products)

    def test_products_can_be_sorted_by_price(self):
        product1 = f.ShopifyProductFactory(user=self.user, store=self.store, price=1.0)
        product2 = f.ShopifyProductFactory(user=self.user, store=self.store, price=2.0)
        product3 = f.ShopifyProductFactory(user=self.user, store=self.store, price=3.0)
        request = Mock()
        request.user = self.user
        request.GET = {}
        items = get_product(request, False, sort='-price')[0]
        products = [item['qelem'] for item in items]
        self.assertEquals([product3, product2, product1], products)

