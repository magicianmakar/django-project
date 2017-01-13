import json

from django.test import TestCase
from django.core.urlresolvers import reverse
from django.core.cache import cache

from mock import Mock, patch

import factories as f

from leadgalaxy.tests.factories import UserFactory


class InvoicePayView(TestCase):
    def setUp(self):
        self.user = UserFactory(username='test')
        self.password = 'test'
        self.user.set_password(self.password)
        self.user.save()
        f.StripeCustomerFactory(user=self.user)
        self.client.login(username=self.user.username, password=self.password)

    def tearDown(self):
        cache.clear()
        cache.close()

    def test_must_be_ajax_only(self):
        r = self.client.post(reverse('invoice_pay', kwargs={'invoice_id': 'a'}))
        self.assertEquals(r.status_code, 500)
        content = json.loads(r.content)
        self.assertEquals(content['error'], 'Bad Request')

    @patch('stripe_subscription.models.stripe.Invoice.retrieve')
    @patch('stripe_subscription.models.User.is_recurring_customer')
    def test_must_handle_stripe_customers_only(self, is_recurring_customer, retrieve):
        is_recurring_customer.return_value = False
        headers = {'HTTP_X_REQUESTED_WITH': 'XMLHttpRequest'}
        r = self.client.post(reverse('invoice_pay', kwargs={'invoice_id': 'a'}), **headers)
        self.assertEquals(r.status_code, 404)
        self.assertFalse(retrieve.called)

    @patch('stripe_subscription.views.get_stripe_invoice')
    @patch('stripe_subscription.models.User.is_recurring_customer')
    def test_invoice_must_exist_or_404(self, is_recurring_customer, get_stripe_invoice):
        is_recurring_customer.return_value = True
        get_stripe_invoice.return_value = None
        headers = {'HTTP_X_REQUESTED_WITH': 'XMLHttpRequest'}
        r = self.client.post(reverse('invoice_pay', kwargs={'invoice_id': 'a'}), **headers)
        self.assertTrue(get_stripe_invoice.called)
        self.assertEquals(r.status_code, 404)

    @patch('stripe_subscription.views.get_stripe_invoice')
    @patch('stripe_subscription.models.User.is_recurring_customer')
    def test_must_return_404_if_customer_doesnt_own_invoice(self, is_recurring_customer, get_stripe_invoice):
        is_recurring_customer.return_value = True
        invoice = Mock()
        invoice.customer = 'nottheuser'
        get_stripe_invoice.return_value = invoice
        headers = {'HTTP_X_REQUESTED_WITH': 'XMLHttpRequest'}
        r = self.client.post(reverse('invoice_pay', kwargs={'invoice_id': 'a'}), **headers)
        self.assertTrue(get_stripe_invoice.called)
        self.assertEquals(r.status_code, 404)

    @patch('stripe_subscription.views.get_stripe_invoice')
    @patch('stripe_subscription.models.User.is_recurring_customer')
    def test_must_return_error_if_invoice_already_paid(self, is_recurring_customer, get_stripe_invoice):
        is_recurring_customer.return_value = True
        invoice = Mock()
        invoice.customer = self.user.stripe_customer.customer_id
        invoice.paid = True
        get_stripe_invoice.return_value = invoice
        headers = {'HTTP_X_REQUESTED_WITH': 'XMLHttpRequest'}
        r = self.client.post(reverse('invoice_pay', kwargs={'invoice_id': 'a'}), **headers)
        self.assertTrue(get_stripe_invoice.called)
        self.assertEquals(r.status_code, 500)

    @patch('stripe_subscription.views.get_stripe_invoice')
    @patch('stripe_subscription.models.User.is_recurring_customer')
    def test_must_return_error_if_invoice_already_closed(self, is_recurring_customer, get_stripe_invoice):
        is_recurring_customer.return_value = True
        invoice = Mock()
        invoice.customer = self.user.stripe_customer.customer_id
        invoice.closed = True
        get_stripe_invoice.return_value = invoice
        headers = {'HTTP_X_REQUESTED_WITH': 'XMLHttpRequest'}
        r = self.client.post(reverse('invoice_pay', kwargs={'invoice_id': 'a'}), **headers)
        self.assertTrue(get_stripe_invoice.called)
        self.assertEquals(r.status_code, 500)

    @patch('stripe_subscription.views.refresh_invoice_cache')
    @patch('stripe_subscription.views.get_stripe_invoice')
    @patch('stripe_subscription.models.User.is_recurring_customer')
    def test_must_return_200_if_no_errors(self, is_recurring_customer, get_stripe_invoice, refresh_invoice_cache):
        is_recurring_customer.return_value = True
        invoice = Mock()
        invoice.customer = self.user.stripe_customer.customer_id
        invoice.closed = False
        invoice.paid = False
        invoice.pay = Mock(return_value=None)
        get_stripe_invoice.return_value = invoice
        headers = {'HTTP_X_REQUESTED_WITH': 'XMLHttpRequest'}
        r = self.client.post(reverse('invoice_pay', kwargs={'invoice_id': 'a'}), **headers)
        self.assertTrue(get_stripe_invoice.called)
        self.assertTrue(refresh_invoice_cache.called)
        self.assertEquals(r.status_code, 200)
