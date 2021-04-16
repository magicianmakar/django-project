import datetime
from decimal import Decimal

import arrow
import stripe.error
from unittest.mock import Mock, patch, PropertyMock

from django.utils import timezone

from lib.test import BaseTestCase

from stripe_subscription import utils
from stripe_subscription.tests import factories as f
from shopified_core.decorators import add_to_class
from leadgalaxy.models import (
    User,
)
from stripe_subscription.models import (
    StripeSubscription,
)
from leadgalaxy.tests.factories import GroupPlanFactory


class StripeCustomerTestCase(BaseTestCase):
    def setUp(self):
        attributes = {
            'date': '1473471324',
            'total': 99,
            'subtotal': 99,
            'lines': {
                'data': [
                    {
                        'amount': 99
                    }
                ]
            },
            'period_start': '1473471324',
            'period_end': '1473471324',
            'discount': {
                'coupon': {
                    'amount_off': 20
                }
            },
            'tax': 40,
            'tax_percent': 50
        }
        self.side_effect = [
            Mock(
                data=[
                    Mock(id=1, **attributes),
                    Mock(id=2, **attributes),
                ],
                has_more=True
            ),
            Mock(
                data=[
                    Mock(id=3, **attributes),
                    Mock(id=4, **attributes),
                ],
                has_more=False
            ),
        ]

    @patch('stripe_subscription.models.stripe.Invoice.list')
    def test_invoices_is_a_cached_property(self, invoice_list):
        invoice_list.side_effect = self.side_effect
        customer = f.StripeCustomerFactory(customer_id='test')
        customer.invoices
        customer.invoices
        customer.invoices
        self.assertEqual(invoice_list.call_count, 2)

    @patch('stripe_subscription.models.stripe.Invoice.list')
    def test_invoices_must_fetch_all_invoices(self, invoice_list):
        invoice_list.side_effect = self.side_effect
        customer = f.StripeCustomerFactory(customer_id='test')
        customer.invoices
        self.assertEqual(len(customer.invoices), 4)

    @patch('stripe_subscription.models.stripe.Invoice.list')
    def test_invoices_must_make_multiple_calls_to_fetch_all(self, invoice_list):
        invoice_list.side_effect = self.side_effect
        customer = f.StripeCustomerFactory(customer_id='test')
        customer.invoices
        self.assertEqual(invoice_list.call_count, 2)

    @patch('stripe_subscription.models.stripe.Invoice.list')
    def test_invoices_next_calls_must_start_after_last_invoice_id(self, invoice_list):
        invoice_list.side_effect = self.side_effect
        customer = f.StripeCustomerFactory(customer_id='test')
        customer.invoices
        invoice_list.assert_called_with(limit=100, customer='test', starting_after=2)

    @patch('stripe_subscription.models.stripe.Invoice.list')
    def test_invoices_can_be_normalized(self, invoice_list):
        invoice_list.side_effect = self.side_effect
        customer = f.StripeCustomerFactory(customer_id='test')
        for invoice in customer.invoices:
            invoice = utils.normalize_invoice(invoice)
            self.assertIsInstance(invoice.date, datetime.datetime)
            self.assertIsInstance(invoice.period_start, datetime.datetime)
            self.assertIsInstance(invoice.period_end, datetime.datetime)
            self.assertIsInstance(invoice.subtotal, Decimal)
            self.assertIsInstance(invoice.total, Decimal)
            self.assertIsInstance(invoice.tax, Decimal)
            self.assertIsInstance(invoice.discount_amount, Decimal)
            for line in invoice.lines.get('data', []):
                self.assertIsInstance(line['amount'], Decimal)

    @patch('stripe_subscription.models.time.sleep')
    @patch('stripe_subscription.models.stripe.Invoice.list')
    def test_invoices_must_sleep_and_wait_for_rate_limit_errors(self, invoice_list, sleep):
        invoice_list.side_effect = (
            stripe.error.RateLimitError('Too many requests made'),
            Mock(data=[], has_more=False)
        )
        customer = f.StripeCustomerFactory(customer_id='test')
        customer.invoices
        self.assertEqual(sleep.call_count, 1)
        self.assertEqual(invoice_list.call_count, 2)

    @patch('leadgalaxy.models.GroupPlan.stripe_plan')
    def test_current_subcription_returns_current_stripe_subscription(self, stripe_plan):
        stripe_id = 'SA_TEST'
        user = User.objects.create_user(username='john', email='john.test@gmail.com', password='123456')
        user.save()
        user.profile.plan = GroupPlanFactory(payment_gateway='stripe')
        stripe_plan.stripe_id = stripe_id
        user.profile.save()

        subscription = StripeSubscription()
        subscription.subscription_id = stripe_id
        subscription.plan = user.profile.plan
        subscription.user = user
        subscription.save()

        stripe_customer = f.StripeCustomerFactory()
        stripe_customer.user = user
        stripe_customer.save()

        user.stripe_customer = stripe_customer
        user.save()

        @add_to_class(StripeSubscription, 'get_main_subscription_item_plan')
        def get_main_subscription_item_plan(self):
            return {'id': stripe_id}

        target = 'stripe_subscription.models.StripeSubscription.subscription'
        with patch(target, new_callable=PropertyMock) as subscription:
            subscription.return_value = {'id': stripe_id, 'object': 'subscription'}
            self.assertEquals(stripe_customer.current_subscription['id'], stripe_id)

    def test_returns_true_if_current_subscription_is_on_trial(self):
        target = 'stripe_subscription.models.StripeCustomer.current_subscription'
        with patch(target, new_callable=PropertyMock) as current_subscription:
            current_subscription.return_value = {'status': 'trialing'}
            stripe_customer = f.StripeCustomerFactory()
            self.assertTrue(stripe_customer.on_trial)

    def test_returns_false_if_current_subscription_is_on_trial(self):
        target = 'stripe_subscription.models.StripeCustomer.current_subscription'
        with patch(target, new_callable=PropertyMock) as current_subscription:
            current_subscription.return_value = {'status': 'nottrialing'}
            stripe_customer = f.StripeCustomerFactory()
            self.assertFalse(stripe_customer.on_trial)

    def test_returns_true_if_current_subscription_is_active(self):
        target = 'stripe_subscription.models.StripeCustomer.current_subscription'
        with patch(target, new_callable=PropertyMock) as current_subscription:
            current_subscription.return_value = {'status': 'active'}
            stripe_customer = f.StripeCustomerFactory()
            self.assertTrue(stripe_customer.is_active)

    def test_trial_days_left_is_zero_if_not_on_trial(self):
        target = 'stripe_subscription.models.StripeCustomer.current_subscription'
        with patch(target, new_callable=PropertyMock) as current_subscription:
            current_subscription.return_value = {'status': 'nottrialing'}
            stripe_customer = f.StripeCustomerFactory()
            self.assertEquals(stripe_customer.trial_days_left, 0)

    def test_trial_days_left_is_zero_if_no_current_subscription(self):
        target = 'stripe_subscription.models.StripeCustomer.current_subscription'
        with patch(target, new_callable=PropertyMock) as current_subscription:
            current_subscription.return_value = None
            stripe_customer = f.StripeCustomerFactory()
            self.assertEquals(stripe_customer.trial_days_left, 0)

    def test_returns_trial_days_left(self):
        target = 'stripe_subscription.models.StripeCustomer.current_subscription'
        with patch(target, new_callable=PropertyMock) as current_subscription:
            trial_days = 5
            trial_end = timezone.now() + datetime.timedelta(days=trial_days)
            trial_end = arrow.get(trial_end).timestamp
            current_subscription.return_value = {'status': 'trialing', 'trial_end': trial_end}
            stripe_customer = f.StripeCustomerFactory()
            self.assertEquals(stripe_customer.trial_days_left, trial_days - 1)

    def test_returns_floor_value_of_trial_days_left(self):
        target = 'stripe_subscription.models.StripeCustomer.current_subscription'
        with patch(target, new_callable=PropertyMock) as current_subscription:
            trial_days = 5
            trial_end = timezone.now() + datetime.timedelta(days=trial_days, hours=1)
            trial_end = arrow.get(trial_end).timestamp
            current_subscription.return_value = {'status': 'trialing', 'trial_end': trial_end}
            stripe_customer = f.StripeCustomerFactory()
            self.assertEquals(stripe_customer.trial_days_left, trial_days)
