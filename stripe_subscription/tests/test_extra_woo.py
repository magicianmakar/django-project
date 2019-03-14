import arrow
from django.core.cache import cache

from lib.test import BaseTestCase

from mock import MagicMock
from mock import patch

from shopified_core import permissions

from stripe_subscription.models import ExtraWooStore, StripeCustomer
from stripe_subscription.utils import have_extra_stores

from leadgalaxy.models import GroupPlan, User, ShopifyStore
from woocommerce_core.models import WooStore


WOO_API_URL = 'https://woo.dropified.com'
WOO_API_KEY = 'ck_4d13e1a939670468e5db05bf360b0016128a27d4'
WOO_API_PASSWORD = 'cs_ad0bd14593670243e03ee22646bfd136e980d4bd'

MYSHOPIFY_DOMAIN = 'shopified-app-ci.myshopify.com'
SHOPIFY_APP_URL = ''


class InvoiceItemMock():
    def __init__(self, invoice_id='ii_1235467890'):
        self.id = invoice_id

    @property
    def id(self):
        return self.id

    @property
    def description(self):
        return ''

    def save(self):
        pass


class ExtraWooStoreTestCase(BaseTestCase):
    def setUp(self):
        self.user = User.objects.create(username='me', email='me@localhost.com')

        self.store = WooStore.objects.create(
            user=self.user, title="test1", api_url=WOO_API_URL,
            api_key=WOO_API_KEY, api_password=WOO_API_PASSWORD)

        self.plan = GroupPlan.objects.create(
            title='Elite New', slug='elite', stores=1,
            payment_gateway=1)

        self.user.profile.change_plan(self.plan)

        self.customer = StripeCustomer.objects.create(
            user=self.user, customer_id='cus_8iACZcJQJuxOta')

        self.user.profile.plan.is_stripe = MagicMock(return_value=True)

    def test_have_extra_stores(self):
        self.assertEqual(self.user.profile.plan, self.plan)

        self.assertTrue(self.user.profile.plan.is_stripe())
        self.assertFalse(have_extra_stores(self.user))

        can_add, total_allowed, user_count = permissions.can_add_store(self.user)
        self.assertTrue(can_add)
        self.assertEqual(total_allowed, self.user.profile.plan.stores)
        self.assertEqual(user_count, self.user.profile.get_woo_stores().count())

        self.assertEqual(self.user.extrawoostore_set.count(), 0)

        ShopifyStore.objects.create(
            user=self.user, title="test2", api_url=SHOPIFY_APP_URL,
            version=2, shop=MYSHOPIFY_DOMAIN)

        self.assertTrue(have_extra_stores(self.user))
        self.assertEqual(self.user.extrastore_set.count(), 1)
        self.assertEqual(self.user.extrawoostore_set.count(), 0)

    def test_extra_woo_store_invoice(self):
        self.assertEqual(self.user.extrawoostore_set.count(), 0)

        extra_woo_store = WooStore.objects.create(
            user=self.user, title="test2", api_url=WOO_API_URL,
            api_key=WOO_API_KEY, api_password=WOO_API_PASSWORD)

        self.assertTrue(have_extra_stores(self.user))
        self.assertEqual(self.user.extrawoostore_set.count(), 1)

        from stripe_subscription import utils

        invoiceitem_id = 'ii_123456789'

        utils.stripe.InvoiceItem.create = MagicMock(return_value=InvoiceItemMock(invoiceitem_id))

        utils.extra_store_invoice(extra_woo_store)

        utils.stripe.InvoiceItem.create.assert_called_once_with(
            amount=2700, currency='usd',
            customer=self.customer.customer_id,
            description=u'Additional WooCommerce Store: {}'.format(extra_woo_store.title)
        )

        extra_woo = ExtraWooStore.objects.get(store=extra_woo_store)
        self.assertEqual(extra_woo.status, 'active')
        self.assertEqual(extra_woo.last_invoice, invoiceitem_id)

    def test_pending_invoice(self):
        WooStore.objects.create(
            user=self.user, title="test2", api_url=WOO_API_URL,
            api_key=WOO_API_KEY, api_password=WOO_API_PASSWORD)

        extra_woo = self.user.extrawoostore_set.first()

        self.assertTrue(extra_woo.status, 'pending')

        from stripe_subscription import utils

        class NextInvoice():
            invoiceitems = ['ii_%d' for i in range(1, 10)]
            invoiceitem_idx = -1

            @property
            def id(self):
                self.invoiceitem_idx += 1
                return self.invoiceitems[self.invoiceitem_idx]

            @property
            def description(self):
                return ''

            def get(self, idx):
                return self.invoiceitems[idx]

            def save(self):
                pass

        invoices = NextInvoice()

        utils.stripe.InvoiceItem.create = MagicMock(return_value=invoices)

        invoiced = utils.invoice_extra_stores()
        self.assertEqual(invoiced, 1)

        extra_woo = self.user.extrawoostore_set.first()
        self.assertEqual(extra_woo.status, 'active', 'Should change the status to active')
        self.assertEqual(extra_woo.last_invoice, NextInvoice().get(0))

        invoiced = utils.invoice_extra_stores()
        self.assertEqual(invoiced, 0, 'Invoice only once in a period')

        with patch.object(utils.arrow, 'utcnow', return_value=arrow.utcnow().replace(days=40)):
            invoiced = utils.invoice_extra_stores()

            extra_woo = self.user.extrawoostore_set.first()
            self.assertEqual(invoiced, 1, 'Invoice after period end')
            self.assertEqual(extra_woo.last_invoice, NextInvoice().get(1), 'Invoice Item should be different')

        with patch.object(utils.arrow, 'utcnow', return_value=arrow.utcnow().replace(days=65)):
            self.assertEqual(utils.invoice_extra_stores(), 1, 'Third billing period Invoice')

        with patch.object(utils.arrow, 'utcnow', return_value=arrow.utcnow().replace(days=89)):
            self.assertEqual(utils.invoice_extra_stores(), 0, 'Still in 3rd billing period')

        with patch.object(utils.arrow, 'utcnow', return_value=arrow.utcnow().replace(days=91)):
            self.assertEqual(utils.invoice_extra_stores(), 1, 'The fourth billing period')
            self.assertEqual(utils.invoice_extra_stores(), 0, 'Should not double invoice this period')

    def test_delete_extra_woo_store_invoice(self):
        # TODO: Handle when the user delete a non-extra store whie having extra stores

        WooStore.objects.create(
            user=self.user, title="test2", api_url=WOO_API_URL,
            api_key=WOO_API_KEY, api_password=WOO_API_PASSWORD)

        extra_woo = self.user.extrawoostore_set.first()

        from stripe_subscription import utils
        utils.stripe.InvoiceItem.create = MagicMock(return_value=InvoiceItemMock())

        self.assertEqual(utils.invoice_extra_stores(), 1, 'Invoice Active store')

        with patch.object(utils.arrow, 'utcnow', return_value=arrow.utcnow().replace(days=35)):
            extra_woo.store.is_active = False
            extra_woo.store.save()

            self.assertEqual(utils.invoice_extra_stores(), 0, 'Do not invcoie delete stores')

    def test_delete_extra_woo_store_on_plan_limit(self):
        WooStore.objects.create(
            user=self.user, title="test2", api_url=WOO_API_URL,
            api_key=WOO_API_KEY, api_password=WOO_API_PASSWORD)

        extra_woo = self.user.extrawoostore_set.first()

        from stripe_subscription import utils
        utils.stripe.InvoiceItem.create = MagicMock(return_value=InvoiceItemMock())

        self.store.is_active = False
        self.store.save()

        self.assertEqual(utils.invoice_extra_stores(), 0, 'Do not invoice delete store')
        self.assertEqual(self.user.extrawoostore_set.first().status, 'disabled')

        extra_woo = WooStore.objects.create(
            user=self.user, title="test3", api_url=WOO_API_URL,
            api_key=WOO_API_KEY, api_password=WOO_API_PASSWORD)

        self.assertEqual(utils.invoice_extra_stores(), 1, 'Invoice Extra Woo Store')
        self.assertEqual(self.user.extrawoostore_set.first().status, 'disabled')
        self.assertEqual(self.user.extrawoostore_set.last().status, 'active')

        with patch.object(utils.arrow, 'utcnow', return_value=arrow.utcnow().replace(days=35)):
            extra_woo.is_active = False
            extra_woo.save()

            self.assertEqual(utils.invoice_extra_stores(), 0, 'Do not invoice delete stores')

    def test_unlimited_plans(self):
        plan = GroupPlan.objects.create(
            title='Unlimited', slug='unlimited', stores=-1,
            payment_gateway=1)

        plan.is_stripe = MagicMock(return_value=True)

        self.user.profile.change_plan(plan)

        self.assertEqual(self.user.profile.plan, plan)

        self.assertTrue(self.user.profile.plan.is_stripe())
        self.assertFalse(have_extra_stores(self.user))

        can_add, total_allowed, user_count = permissions.can_add_store(self.user)
        self.assertTrue(can_add)
        self.assertEqual(total_allowed, self.user.profile.plan.stores)
        self.assertEqual(user_count, self.user.profile.get_woo_stores().count())

        self.assertEqual(self.user.extrawoostore_set.count(), 0)

        for i in range(10):
            WooStore.objects.create(
                user=self.user, title="test%s" % i, api_url=WOO_API_URL,
                api_key=WOO_API_KEY, api_password=WOO_API_PASSWORD)

        self.assertTrue(self.user.profile.get_woo_stores().count() >= 10)

        self.assertFalse(have_extra_stores(self.user))
        self.assertEqual(self.user.extrawoostore_set.count(), 0)

    def test_not_generate_invoice_on_plan_limits_increase(self):
        for i in range(10):
            WooStore.objects.create(
                user=self.user, title="test%s" % i, api_url=WOO_API_URL,
                api_key=WOO_API_KEY, api_password=WOO_API_PASSWORD)
        self.assertTrue(have_extra_stores(self.user))

        from stripe_subscription import utils
        utils.stripe.InvoiceItem.create = MagicMock(return_value=InvoiceItemMock())

        cache.delete('user_extra_stores_ignored_{}'.format(self.user.id))
        cache.delete('user_invoice_checked_{}'.format(self.user.id))
        self.assertEqual(utils.invoice_extra_stores(), 10, 'Invoice Active store')

        # Change plan
        plan = GroupPlan.objects.create(
            title='Elite 10', slug='elite-ten-stores', stores=10,
            payment_gateway=1)
        plan.is_stripe = MagicMock(return_value=True)
        self.user.profile.change_plan(plan)
        self.assertEqual(self.user.profile.plan, plan)

        # Check if invoice will be generated in the next period
        with patch.object(utils.arrow, 'utcnow', return_value=arrow.utcnow().replace(days=40)):
            cache.delete('user_extra_stores_ignored_{}'.format(self.user.id))
            cache.delete('user_invoice_checked_{}'.format(self.user.id))
            self.assertEqual(utils.invoice_extra_stores(), 1)
            self.assertEqual(self.user.extrawoostore_set.count(), 1)
