import json

from django.test import TestCase
from django.core.urlresolvers import reverse
from django.core.cache import cache
from django.conf import settings

from mock import Mock, patch

import factory
import factory.fuzzy

from stripe_subscription.models import StripeCustomer


class UserFactory(factory.django.DjangoModelFactory):
    username = factory.fuzzy.FuzzyText()
    first_name = factory.fuzzy.FuzzyText()
    last_name = factory.fuzzy.FuzzyText()
    is_active = True

    class Meta:
        model = settings.AUTH_USER_MODEL


class StripeCustomerFactory(factory.django.DjangoModelFactory):
    user = factory.SubFactory('stripe_subscription.tests.test_models.UserFactory')
    customer_id = factory.fuzzy.FuzzyText()

    class Meta:
        model = StripeCustomer


class InvoicePayView(TestCase):
    def setUp(self):
        self.user = UserFactory(username='test')
        self.password = 'test'
        self.user.set_password(self.password)
        self.user.save()
        StripeCustomerFactory(user=self.user)
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
    @patch('stripe_subscription.models.User.is_stripe_customer')
    def test_must_handle_stripe_customers_only(self, is_stripe_customer, retrieve):
        is_stripe_customer.return_value = False
        headers = {'HTTP_X_REQUESTED_WITH': 'XMLHttpRequest'}
        r = self.client.post(reverse('invoice_pay', kwargs={'invoice_id': 'a'}), **headers)
        self.assertEquals(r.status_code, 404)
        self.assertFalse(retrieve.called)

    @patch('stripe_subscription.views.get_stripe_invoice')
    @patch('stripe_subscription.models.User.is_stripe_customer')
    def test_invoice_must_exist_or_404(self, is_stripe_customer, get_stripe_invoice):
        is_stripe_customer.return_value = True
        get_stripe_invoice.return_value = None
        headers = {'HTTP_X_REQUESTED_WITH': 'XMLHttpRequest'}
        r = self.client.post(reverse('invoice_pay', kwargs={'invoice_id': 'a'}), **headers)
        self.assertTrue(get_stripe_invoice.called)
        self.assertEquals(r.status_code, 404)

    @patch('stripe_subscription.views.get_stripe_invoice')
    @patch('stripe_subscription.models.User.is_stripe_customer')
    def test_must_return_404_if_customer_doesnt_own_invoice(
                self, is_stripe_customer, get_stripe_invoice):
        is_stripe_customer.return_value = True
        invoice = Mock()
        invoice.customer = 'nottheuser'
        get_stripe_invoice.return_value = invoice
        headers = {'HTTP_X_REQUESTED_WITH': 'XMLHttpRequest'}
        r = self.client.post(reverse('invoice_pay', kwargs={'invoice_id': 'a'}), **headers)
        self.assertTrue(get_stripe_invoice.called)
        self.assertEquals(r.status_code, 404)

    @patch('stripe_subscription.views.get_stripe_invoice')
    @patch('stripe_subscription.models.User.is_stripe_customer')
    def test_must_return_error_if_invoice_already_paid(
                self, is_stripe_customer, get_stripe_invoice):
        is_stripe_customer.return_value = True
        invoice = Mock()
        invoice.customer = self.user.stripe_customer.customer_id
        invoice.paid = True
        get_stripe_invoice.return_value = invoice
        headers = {'HTTP_X_REQUESTED_WITH': 'XMLHttpRequest'}
        r = self.client.post(reverse('invoice_pay', kwargs={'invoice_id': 'a'}), **headers)
        self.assertTrue(get_stripe_invoice.called)
        self.assertEquals(r.status_code, 500)

    @patch('stripe_subscription.views.get_stripe_invoice')
    @patch('stripe_subscription.models.User.is_stripe_customer')
    def test_must_return_error_if_invoice_already_closed(
                self, is_stripe_customer, get_stripe_invoice):
        is_stripe_customer.return_value = True
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
    @patch('stripe_subscription.models.User.is_stripe_customer')
    def test_must_return_200_if_no_errors(
            self, is_stripe_customer, get_stripe_invoice, refresh_invoice_cache):
        is_stripe_customer.return_value = True
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

