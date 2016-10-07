import datetime
from decimal import Decimal

import stripe.error
from mock import Mock, patch

from django.test import TestCase

from stripe_subscription import utils
from stripe_subscription.tests import factories as f


class StripeCustomerTestCase(TestCase):
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
        self.assertEquals(invoice_list.call_count, 2)

    @patch('stripe_subscription.models.stripe.Invoice.list')
    def test_invoices_must_fetch_all_invoices(self, invoice_list):
        invoice_list.side_effect = self.side_effect
        customer = f.StripeCustomerFactory(customer_id='test')
        customer.invoices
        self.assertEquals(len(customer.invoices), 4)

    @patch('stripe_subscription.models.stripe.Invoice.list')
    def test_invoices_must_make_multiple_calls_to_fetch_all(self, invoice_list):
        invoice_list.side_effect = self.side_effect
        customer = f.StripeCustomerFactory(customer_id='test')
        customer.invoices
        self.assertEquals(invoice_list.call_count, 2)

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
    def test_invoices_must_sleep_and_wait_for_rate_limit_errors(
                self, invoice_list, sleep):
        invoice_list.side_effect = (
            stripe.error.RateLimitError('Too many requests made'),
            Mock(data=[], has_more=False)
        )
        customer = f.StripeCustomerFactory(customer_id='test')
        customer.invoices
        self.assertEquals(sleep.call_count, 1)
        self.assertEquals(invoice_list.call_count, 2)
