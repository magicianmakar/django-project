from unittest.mock import patch

from django.urls import reverse

from lib.test import BaseTestCase
from leadgalaxy.tests.factories import (
    AppPermissionFactory,
    ShopifyStoreFactory,
    UserFactory,
)

from commercehq_core.tests.factories import CommerceHQStoreFactory
from gearbubble_core.tests.factories import GearBubbleStoreFactory
from groovekart_core.tests.factories import GrooveKartStoreFactory
from woocommerce_core.tests.factories import WooStoreFactory


class GotoPageTestCase(BaseTestCase):
    def setUp(self):
        self.user = UserFactory(username='test')
        self.password = 'test'
        self.user.set_password(self.password)
        self.user.save()

        self.client.login(username=self.user.username, password=self.password)
        self.shopify_url = reverse('goto-page', kwargs={'url_name': 'orders'})
        self.url = reverse('goto-page', kwargs={'url_name': 'orders_list'})

    def add_user_permission(self, perm):
        permission = AppPermissionFactory(name=perm)
        self.user.profile.plan.permissions.add(permission)
        self.user.profile.save()

    def make_url(self, name):
        return f'{reverse(name)}?store={self.store.id}'

    def test_shopify(self):
        self.store = ShopifyStoreFactory(user=self.user)
        response = self.client.get(self.shopify_url)
        self.assertRedirects(response, self.make_url('orders'))

    @patch('commercehq_core.views.OrdersList.paginator_class'
           '._orders_count_request')
    def test_chq(self, mock_count_request):
        mock_count_request.return_value = {
            '_meta': {'totalCount': 0, 'pageCount': 0}
        }

        self.store = CommerceHQStoreFactory(user=self.user)
        self.add_user_permission('commercehq.use')
        response = self.client.get(self.url)
        self.assertRedirects(response, self.make_url('chq:orders_list'))

    def test_gear(self):
        self.store = GearBubbleStoreFactory(user=self.user)
        self.add_user_permission('gearbubble.use')
        response = self.client.get(self.url)
        self.assertRedirects(response, self.make_url('gear:orders_list'))

    def test_gkart(self):
        self.store = GrooveKartStoreFactory(user=self.user)
        self.add_user_permission('groovekart.use')
        response = self.client.get(self.url)
        self.assertRedirects(response, self.make_url('gkart:orders_list'))

    def test_woo(self):
        self.store = WooStoreFactory(user=self.user)
        self.add_user_permission('woocommerce.use')
        response = self.client.get(self.url)
        self.assertRedirects(response, self.make_url('woo:orders_list'))

    @patch('commercehq_core.views.OrdersList.paginator_class'
           '._orders_count_request')
    def test_multiple_stores(self, mock_count_request):
        mock_count_request.return_value = {
            '_meta': {'totalCount': 0, 'pageCount': 0}
        }

        self.stores = [
            CommerceHQStoreFactory(user=self.user),
            GearBubbleStoreFactory(user=self.user),
            GrooveKartStoreFactory(user=self.user),
            WooStoreFactory(user=self.user),
        ]
        self.store = self.stores[0]
        self.add_user_permission('commercehq.use')
        self.add_user_permission('gearbubble.use')
        self.add_user_permission('groovekart.use')
        self.add_user_permission('woocommerce.use')
        response = self.client.get(self.url)
        self.assertRedirects(response, self.make_url('chq:orders_list'))

    def test_zero_store(self):
        response = self.client.get(self.shopify_url)
        self.assertRedirects(response, '/')

        response = self.client.get(self.url)
        self.assertRedirects(response, '/')
