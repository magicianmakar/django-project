from django.test import TestCase

from mock import MagicMock
from mock import patch
from munch import Munch

from stripe_subscription.models import ExtraStore, StripeCustomer
from stripe_subscription.utils import have_extra_stores

from leadgalaxy.models import GroupPlan, ShopifyStore, User

MYSHOPIFY_DOMAIN = 'shopified-app-ci.myshopify.com'
SHOPIFY_APP_URL = ':88937df17024aa5126203507e2147f47@%s' % MYSHOPIFY_DOMAIN


class ExtraStoreTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create(username='me', email='me@localhost.com')

        self.store = ShopifyStore.objects.create(
            user=self.user, title="test1", api_url=SHOPIFY_APP_URL,
            version=2, shop=MYSHOPIFY_DOMAIN)

        self.plan = GroupPlan.objects.create(
            title='Elite', slug='elite', stores=1,
            payment_gateway=1)

        self.user.profile.change_plan(self.plan)

        self.customer = StripeCustomer.objects.create(
            user=self.user, customer_id='cus_8iACZcJQJuxOta')

        self.user.profile.plan.is_stripe = MagicMock(return_value=True)

    def test_have_extra_stores(self):
        self.assertEqual(self.user.profile.plan, self.plan)

        self.assertTrue(self.user.profile.plan.is_stripe())
        self.assertFalse(have_extra_stores(self.user))

        can_add, total_allowed, user_count = self.user.profile.can_add_store()
        self.assertTrue(can_add)
        self.assertEqual(total_allowed, self.user.profile.plan.stores)
        self.assertEqual(user_count, self.user.profile.get_active_stores().count())

        self.assertEqual(self.user.extrastore_set.count(), 0)

        ShopifyStore.objects.create(
            user=self.user, title="test2", api_url=SHOPIFY_APP_URL,
            version=2, shop=MYSHOPIFY_DOMAIN)

        self.assertTrue(have_extra_stores(self.user))
        self.assertEqual(self.user.extrastore_set.count(), 1)

    def test_extra_store_invoice(self):
        self.assertEqual(self.user.extrastore_set.count(), 0)

        extra_store = ShopifyStore.objects.create(
            user=self.user, title="test2", api_url=SHOPIFY_APP_URL,
            version=2, shop=MYSHOPIFY_DOMAIN)

        self.assertTrue(have_extra_stores(self.user))
        self.assertEqual(self.user.extrastore_set.count(), 1)

        from stripe_subscription import utils

        invoiceitem_id = 'ii_123456789'

        utils.stripe.InvoiceItem.create = MagicMock(return_value=Munch({'id': invoiceitem_id}))

        utils.extra_store_invoice(extra_store)

        utils.stripe.InvoiceItem.create.assert_called_once_with(
            amount=2700, currency='usd',
            customer=self.customer.customer_id,
            description=u'Additional Store: {}'.format(extra_store.title)
        )

        extra = ExtraStore.objects.get(store=extra_store)
        self.assertEqual(extra.status, 'active')
        self.assertEqual(extra.last_invoice, invoiceitem_id)

    def test_pending_invoice(self):
        ShopifyStore.objects.create(
            user=self.user, title="test2", api_url=SHOPIFY_APP_URL,
            version=2, shop=MYSHOPIFY_DOMAIN)

        extra = self.user.extrastore_set.first()

        self.assertTrue(extra.status, 'pending')

        from stripe_subscription import utils

        class NextInvoice():
            invoiceitems = ['ii_%d' for i in range(1, 10)]
            invoiceitem_idx = -1

            @property
            def id(self):
                self.invoiceitem_idx += 1
                return self.invoiceitems[self.invoiceitem_idx]

            def get(self, idx):
                return self.invoiceitems[idx]
        invoices = NextInvoice()

        utils.stripe.InvoiceItem.create = MagicMock(return_value=invoices)

        invoiced = utils.invoice_extra_stores()
        self.assertEqual(invoiced, 1)

        extra = self.user.extrastore_set.first()
        self.assertEqual(extra.status, 'active', 'Should change the status to active')
        self.assertEqual(extra.last_invoice, NextInvoice().get(0))

        invoiced = utils.invoice_extra_stores()
        self.assertEqual(invoiced, 0, 'Invoice only once in a period')

        import arrow
        with patch.object(utils.arrow, 'utcnow', return_value=arrow.utcnow().replace(days=40)):
            invoiced = utils.invoice_extra_stores()

            extra = self.user.extrastore_set.first()
            self.assertEqual(invoiced, 1, 'Invoice after period end')
            self.assertEqual(extra.last_invoice, NextInvoice().get(1), 'Invoice Item should be different')

        with patch.object(utils.arrow, 'utcnow', return_value=arrow.utcnow().replace(days=65)):
            self.assertEqual(utils.invoice_extra_stores(), 1, 'Third billing period Invoice')

        with patch.object(utils.arrow, 'utcnow', return_value=arrow.utcnow().replace(days=89)):
            self.assertEqual(utils.invoice_extra_stores(), 0, 'Still in 3rd billing period')

        with patch.object(utils.arrow, 'utcnow', return_value=arrow.utcnow().replace(days=91)):
            self.assertEqual(utils.invoice_extra_stores(), 1, 'The fourth billing period')
            self.assertEqual(utils.invoice_extra_stores(), 0, 'Should not double invoice this period')

    def test_delete_extra_store_invoice(self):
        # TODO: Handle when the user delete a non-extra store whie having extra stores

        ShopifyStore.objects.create(
            user=self.user, title="test2", api_url=SHOPIFY_APP_URL,
            version=2, shop=MYSHOPIFY_DOMAIN)

        extra = self.user.extrastore_set.first()

        from stripe_subscription import utils
        utils.stripe.InvoiceItem.create = MagicMock(return_value=Munch({'id': 'invoiceitem_id'}))

        self.assertEqual(utils.invoice_extra_stores(), 1, 'Invoice Active store')

        import arrow
        with patch.object(utils.arrow, 'utcnow', return_value=arrow.utcnow().replace(days=35)):
            extra.store.is_active = False
            extra.store.save()

            self.assertEqual(utils.invoice_extra_stores(), 0, 'Do not invcoie delete stores')

    def test_delete_extra_store_on_plan_limit(self):
        ShopifyStore.objects.create(
            user=self.user, title="test2", api_url=SHOPIFY_APP_URL,
            version=2, shop=MYSHOPIFY_DOMAIN)

        extra = self.user.extrastore_set.first()

        from stripe_subscription import utils
        utils.stripe.InvoiceItem.create = MagicMock(return_value=Munch({'id': 'invoiceitem_id'}))

        self.store.is_active = False
        self.store.save()

        self.assertEqual(utils.invoice_extra_stores(), 0, 'Do not invcoie delete store')
        self.assertEqual(self.user.extrastore_set.first().status, 'disabled')

        extra = ShopifyStore.objects.create(
            user=self.user, title="test3", api_url=SHOPIFY_APP_URL,
            version=2, shop=MYSHOPIFY_DOMAIN)

        self.assertEqual(utils.invoice_extra_stores(), 1, 'Invoice Extra Store')
        self.assertEqual(self.user.extrastore_set.first().status, 'disabled')
        self.assertEqual(self.user.extrastore_set.last().status, 'active')

        import arrow
        with patch.object(utils.arrow, 'utcnow', return_value=arrow.utcnow().replace(days=35)):
            extra.is_active = False
            extra.save()

            self.assertEqual(utils.invoice_extra_stores(), 0, 'Do not invcoie delete stores')
            self.assertEqual(self.user.extrastore_set.last().status, 'disabled')

    def test_unlimited_plans(self):
        plan = GroupPlan.objects.create(
            title='Unlimited', slug='unlimited', stores=-1,
            payment_gateway=1)

        plan.is_stripe = MagicMock(return_value=True)

        self.user.profile.change_plan(plan)

        self.assertEqual(self.user.profile.plan, plan)

        self.assertTrue(self.user.profile.plan.is_stripe())
        self.assertFalse(have_extra_stores(self.user))

        can_add, total_allowed, user_count = self.user.profile.can_add_store()
        self.assertTrue(can_add)
        self.assertEqual(total_allowed, self.user.profile.plan.stores)
        self.assertEqual(user_count, self.user.profile.get_active_stores().count())

        self.assertEqual(self.user.extrastore_set.count(), 0)

        for i in range(10):
            ShopifyStore.objects.create(
                user=self.user, title="test%s" % i, api_url=SHOPIFY_APP_URL,
                version=2, shop=MYSHOPIFY_DOMAIN)

        self.assertTrue(self.user.profile.get_active_stores().count() >= 10)

        self.assertFalse(have_extra_stores(self.user))
        self.assertEqual(self.user.extrastore_set.count(), 0)
