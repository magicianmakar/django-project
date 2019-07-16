from decimal import Decimal
from unittest.mock import patch

from munch import Munch
import requests_mock

from django.urls import reverse

from lib.test import BaseTestCase
from analytic_events.models import PlanSelectionEvent
from leadgalaxy.tests import factories as f
from shopified_core.utils import random_hash


class ShopifyApssSubscriprtionTestCase(BaseTestCase):
    def setUp(self):
        self.user = f.UserFactory(username='test')
        self.password = 'test'
        self.user.set_password(self.password)
        self.user.save()

        self.plan = f.GroupPlanFactory()

        self.client.login(username=self.user.username, password=self.password)

    def test_shopify_plan_without_store(self):
        data = {'plan': self.plan.id}
        r = self.client.post(reverse('shopify_subscription.views.subscription_plan'), data)

        self.assertEqual(r.status_code, 422)
        self.assertEqual(r.json()['error'], "Please make sure you've added your store")

    def test_non_found_plan(self):
        self.store = f.ShopifyStoreFactory(user=self.user)

        data = {'plan': self.plan.id + 1000}
        r = self.client.post(reverse('shopify_subscription.views.subscription_plan'), data)

        self.assertEqual(r.status_code, 404)
        self.assertEqual(r.json()['error'], 'Selected plan not found')

    def test_non_shopify_plan(self):
        self.store = f.ShopifyStoreFactory(user=self.user)

        data = {'plan': self.plan.id}
        r = self.client.post(reverse('shopify_subscription.views.subscription_plan'), data)

        self.assertEqual(r.status_code, 422)
        self.assertEqual(r.json()['error'], 'Plan is not valid')

    @requests_mock.Mocker()
    @patch('leadgalaxy.models.ShopifyStore.shopify.RecurringApplicationCharge.create')
    @patch('leadgalaxy.models.ShopifyStore.shopify')
    @patch('shopify_subscription.models.ShopifySubscription.refresh')
    def test_shopify_plan_sub_monthly(self, req_mock, refresh, shopify, recu_charge_create):
        self.store = f.ShopifyStoreFactory(user=self.user)

        req_mock.get(self.store.get_link('/admin/shop.json', api=True), json={"shop": {"plan_name": "pro"}})
        confirm_hash = random_hash()
        recu_charge_create.return_value = Munch({
            'id': 123456789,
            'status': 'pending',
            'confirmation_url': self.store.get_link(f'/admin/charges/1029266950/confirm_recurring_application_charge?signature={confirm_hash}')})

        self.plan = f.GroupPlanFactory(
            default_plan=0,
            payment_gateway='shopify',
            payment_interval='monthly',
            monthly_price=Decimal('50.00'))

        data = {'plan': self.plan.id}
        r = self.client.post(reverse('shopify_subscription.views.subscription_plan'), data)

        self.assertEqual(r.status_code, 200)
        self.assertIn('location', r.json(), 'Respond with charge confirmation url')
        self.assertIn(confirm_hash, r.json()['location'])

        recu_charge_create.assert_called_once()
        self.assertEqual(recu_charge_create.call_args[0][0]['price'], self.plan.monthly_price, 'Plan monthly price'),
        self.assertNotIn('Shopify Staff 50% Discount', recu_charge_create.call_args[0][0]['name'], 'Discount should not be in Charge title'),

        refresh.assert_called_once()
        refresh.assert_called_with(sub=recu_charge_create.return_value)

        self.assertEqual(PlanSelectionEvent.objects.count(), 1, 'Plan selection event')

    @requests_mock.Mocker()
    @patch('leadgalaxy.models.ShopifyStore.shopify.ApplicationCharge.create')
    @patch('leadgalaxy.models.ShopifyStore.shopify')
    @patch('shopify_subscription.models.ShopifySubscription.refresh')
    def test_shopify_plan_sub_yearly(self, req_mock, refresh, shopify, charge_create):
        self.store = f.ShopifyStoreFactory(user=self.user)

        req_mock.get(self.store.get_link('/admin/shop.json', api=True), json={"shop": {"plan_name": "pro"}})
        confirm_hash = random_hash()
        charge_create.return_value = Munch({
            'id': 123456789,
            'status': 'pending',
            'confirmation_url': self.store.get_link(f'/admin/charges/1029266950/confirm_recurring_application_charge?signature={confirm_hash}')})

        self.plan = f.GroupPlanFactory(
            default_plan=0,
            payment_gateway='shopify',
            payment_interval='yearly',
            monthly_price=Decimal('50.00'))

        data = {'plan': self.plan.id}
        r = self.client.post(reverse('shopify_subscription.views.subscription_plan'), data)

        self.assertEqual(r.status_code, 200)
        self.assertIn('location', r.json(), 'Respond with charge confirmation url')
        self.assertIn(confirm_hash, r.json()['location'])

        charge_create.assert_called_once()
        self.assertEqual(charge_create.call_args[0][0]['price'], self.plan.monthly_price * 12, 'Yearly price should be x12 monthly price'),
        self.assertNotIn('Shopify Staff 50% Discount', charge_create.call_args[0][0]['name'], 'Discount should not be in Charge title'),

        refresh.assert_called_once()
        refresh.assert_called_with(sub=charge_create.return_value)

        self.assertEqual(PlanSelectionEvent.objects.count(), 1, 'Plan selection event')

    @requests_mock.Mocker()
    @patch('leadgalaxy.models.ShopifyStore.shopify.RecurringApplicationCharge.create')
    @patch('leadgalaxy.models.ShopifyStore.shopify')
    @patch('shopify_subscription.models.ShopifySubscription.refresh')
    def test_shopify_plan_sub_monthly_shopify_staff(self, req_mock, refresh, shopify, recu_charge_create):
        self.store = f.ShopifyStoreFactory(user=self.user)

        req_mock.get(self.store.get_link('/admin/shop.json', api=True), json={"shop": {"plan_name": "staff"}})

        confirm_hash = random_hash()
        recu_charge_create.return_value = Munch({
            'id': 123456789,
            'status': 'pending',
            'confirmation_url': self.store.get_link(f'/admin/charges/1029266950/confirm_recurring_application_charge?signature={confirm_hash}')})

        self.plan = f.GroupPlanFactory(
            default_plan=0,
            payment_gateway='shopify',
            payment_interval='monthly',
            monthly_price=Decimal('50.00'))

        data = {'plan': self.plan.id}
        r = self.client.post(reverse('shopify_subscription.views.subscription_plan'), data)

        # req_mock.assert_called_with(a=1)
        self.assertEqual(r.status_code, 200)
        self.assertIn('location', r.json(), 'Respond with charge confirmation url')
        self.assertIn(confirm_hash, r.json()['location'])

        recu_charge_create.assert_called_once()
        self.assertEqual(recu_charge_create.call_args[0][0]['price'], self.plan.monthly_price / 2, 'Plan monthly price with 50% off'),
        self.assertIn('Shopify Staff 50% Discount', recu_charge_create.call_args[0][0]['name'], 'Discount in Charge title'),

        refresh.assert_called_once()
        refresh.assert_called_with(sub=recu_charge_create.return_value)

        self.assertEqual(PlanSelectionEvent.objects.count(), 1, 'Plan selection event')

    #

    @requests_mock.Mocker()
    @patch('leadgalaxy.models.ShopifyStore.shopify.ApplicationCharge.create')
    @patch('leadgalaxy.models.ShopifyStore.shopify')
    @patch('shopify_subscription.models.ShopifySubscription.refresh')
    def test_shopify_plan_sub_yearly_shopify_staff(self, req_mock, refresh, shopify, charge_create):
        self.store = f.ShopifyStoreFactory(user=self.user)

        req_mock.get(self.store.get_link('/admin/shop.json', api=True), json={"shop": {"plan_name": "staff"}})
        confirm_hash = random_hash()
        charge_create.return_value = Munch({
            'id': 123456789,
            'status': 'pending',
            'confirmation_url': self.store.get_link(f'/admin/charges/1029266950/confirm_recurring_application_charge?signature={confirm_hash}')})

        self.plan = f.GroupPlanFactory(
            default_plan=0,
            payment_gateway='shopify',
            payment_interval='yearly',
            monthly_price=Decimal('50.00'))

        data = {'plan': self.plan.id}
        r = self.client.post(reverse('shopify_subscription.views.subscription_plan'), data)

        self.assertEqual(r.status_code, 200)
        self.assertIn('location', r.json(), 'Respond with charge confirmation url')
        self.assertIn(confirm_hash, r.json()['location'])

        charge_create.assert_called_once()
        self.assertEqual(charge_create.call_args[0][0]['price'], (self.plan.monthly_price * 12) / 2, 'Price should be x6 monthly price for staff'),
        self.assertIn('Shopify Staff 50% Discount', charge_create.call_args[0][0]['name'], 'Discount should be in Charge title'),

        refresh.assert_called_once()
        refresh.assert_called_with(sub=charge_create.return_value)

        self.assertEqual(PlanSelectionEvent.objects.count(), 1, 'Plan selection event')

    @requests_mock.Mocker()
    @patch('leadgalaxy.models.ShopifyStore.shopify.RecurringApplicationCharge.create')
    @patch('leadgalaxy.models.ShopifyStore.shopify')
    @patch('phone_automation.billing_utils.get_shopify_recurring')
    def test_shopify_subscription_callflex(self, req_mock, get_shopify_recurring, shopify, recu_charge_create):
        self.store = f.ShopifyStoreFactory(user=self.user)
        req_mock.get(self.store.get_link('/admin/shop.json', api=True), json={"shop": {"plan_name": "pro"}})
        confirm_hash = random_hash()
        get_shopify_recurring.return_value = False
        recu_charge_create.return_value = Munch({
            'id': 123456789,
            'status': 'pending',
            'confirmation_url': self.store.get_link(f'/admin/charges/1029266950/confirm_recurring_application_charge?signature={confirm_hash}')})

        data = {}
        r = self.client.post(reverse('shopify_subscription.views.subscription_callflex'), data)

        self.assertEqual(r.status_code, 200)
        self.assertIn('location', r.json(), 'Respond with charge confirmation url')
        self.assertIn(confirm_hash, r.json()['location'])

        recu_charge_create.assert_called_once()
        self.assertEqual(recu_charge_create.call_args[0][0]['price'], 0, 'Plan monthly price'),

        get_shopify_recurring.assert_called_once()

    @requests_mock.Mocker()
    @patch('leadgalaxy.models.ShopifyStore.shopify.RecurringApplicationCharge.create')
    @patch('leadgalaxy.models.ShopifyStore.shopify')
    @patch('phone_automation.billing_utils.get_shopify_recurring')
    def test_shopify_subscription_callflex_exists(self, req_mock, get_shopify_recurring, shopify, recu_charge_create):
        self.store = f.ShopifyStoreFactory(user=self.user)

        req_mock.get(self.store.get_link('/admin/shop.json', api=True), json={"shop": {"plan_name": "pro"}})
        confirm_hash = random_hash()
        get_shopify_recurring.return_value = Munch({
            'id': 123456789,
            'status': 'active'})

        recu_charge_create.return_value = Munch({
            'id': 123456789,
            'status': 'pending',
            'confirmation_url': self.store.get_link(f'/admin/charges/1029266950/confirm_recurring_application_charge?signature={confirm_hash}')})

        data = {}
        r = self.client.post(reverse('shopify_subscription.views.subscription_callflex'), data)

        self.assertEqual(r.status_code, 422)
        self.assertIn('error', r.json(), 'Respond with error')

        recu_charge_create.assert_not_called()
        get_shopify_recurring.assert_called_once()
