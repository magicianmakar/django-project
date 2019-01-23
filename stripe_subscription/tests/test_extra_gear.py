from lib.test import BaseTestCase

from mock import MagicMock
from mock import patch

from shopified_core import permissions

from stripe_subscription.models import ExtraGearStore, StripeCustomer
from stripe_subscription.utils import have_extra_stores

from leadgalaxy.models import GroupPlan, User, ShopifyStore
from gearbubble_core.models import GearBubbleStore


GEAR_API_TOKEN = '2cdf24eecbfc4496be5b716502d42db3'
GEAR_API_MODE = GearBubbleStore.STAGING

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


class ExtraGearStoreTestCase(BaseTestCase):
    def setUp(self):
        self.user = User.objects.create(username='me', email='me@localhost.com')

        self.store = GearBubbleStore.objects.create(
            user=self.user, title="test1", api_token=GEAR_API_TOKEN,
            mode=GEAR_API_MODE)

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

        can_add, total_allowed, user_count = permissions.can_add_store(self.user)
        self.assertTrue(can_add)
        self.assertEqual(total_allowed, self.user.profile.plan.stores)
        self.assertEqual(user_count, self.user.profile.get_gear_stores().count())

        self.assertEqual(self.user.extragearstore_set.count(), 0)

        ShopifyStore.objects.create(
            user=self.user, title="test2", api_url=SHOPIFY_APP_URL,
            version=2, shop=MYSHOPIFY_DOMAIN)

        self.assertTrue(have_extra_stores(self.user))
        self.assertEqual(self.user.extrastore_set.count(), 1)
        self.assertEqual(self.user.extragearstore_set.count(), 0)

    def test_extra_gear_store_invoice(self):
        self.assertEqual(self.user.extragearstore_set.count(), 0)

        extra_gear_store = GearBubbleStore.objects.create(
            user=self.user, title="test2", api_token=GEAR_API_TOKEN,
            mode=GEAR_API_MODE)

        self.assertTrue(have_extra_stores(self.user))
        self.assertEqual(self.user.extragearstore_set.count(), 1)

        from stripe_subscription import utils

        invoiceitem_id = 'ii_123456789'

        utils.stripe.InvoiceItem.create = MagicMock(return_value=InvoiceItemMock(invoiceitem_id))

        utils.extra_store_invoice(extra_gear_store)

        utils.stripe.InvoiceItem.create.assert_called_once_with(
            amount=2700, currency='usd',
            customer=self.customer.customer_id,
            description=u'Additional GearBubble Store: {}'.format(extra_gear_store.title)
        )

        extra_gear = ExtraGearStore.objects.get(store=extra_gear_store)
        self.assertEqual(extra_gear.status, 'active')
        self.assertEqual(extra_gear.last_invoice, invoiceitem_id)

    def test_pending_invoice(self):
        GearBubbleStore.objects.create(
            user=self.user, title="test2", api_token=GEAR_API_TOKEN,
            mode=GEAR_API_MODE)

        extra_gear = self.user.extragearstore_set.first()

        self.assertTrue(extra_gear.status, 'pending')

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

        extra_gear = self.user.extragearstore_set.first()
        self.assertEqual(extra_gear.status, 'active', 'Should change the status to active')
        self.assertEqual(extra_gear.last_invoice, NextInvoice().get(0))

        invoiced = utils.invoice_extra_stores()
        self.assertEqual(invoiced, 0, 'Invoice only once in a period')

        import arrow
        with patch.object(utils.arrow, 'utcnow', return_value=arrow.utcnow().replace(days=40)):
            invoiced = utils.invoice_extra_stores()

            extra_gear = self.user.extragearstore_set.first()
            self.assertEqual(invoiced, 1, 'Invoice after period end')
            self.assertEqual(extra_gear.last_invoice, NextInvoice().get(1), 'Invoice Item should be different')

        with patch.object(utils.arrow, 'utcnow', return_value=arrow.utcnow().replace(days=65)):
            self.assertEqual(utils.invoice_extra_stores(), 1, 'Third billing period Invoice')

        with patch.object(utils.arrow, 'utcnow', return_value=arrow.utcnow().replace(days=89)):
            self.assertEqual(utils.invoice_extra_stores(), 0, 'Still in 3rd billing period')

        with patch.object(utils.arrow, 'utcnow', return_value=arrow.utcnow().replace(days=91)):
            self.assertEqual(utils.invoice_extra_stores(), 1, 'The fourth billing period')
            self.assertEqual(utils.invoice_extra_stores(), 0, 'Should not double invoice this period')

    def test_delete_extra_gear_store_invoice(self):
        # TODO: Handle when the user delete a non-extra store whie having extra stores

        GearBubbleStore.objects.create(
            user=self.user, title="test2", api_token=GEAR_API_TOKEN,
            mode=GEAR_API_MODE)

        extra_gear = self.user.extragearstore_set.first()

        from stripe_subscription import utils
        utils.stripe.InvoiceItem.create = MagicMock(return_value=InvoiceItemMock())

        self.assertEqual(utils.invoice_extra_stores(), 1, 'Invoice Active store')

        import arrow
        with patch.object(utils.arrow, 'utcnow', return_value=arrow.utcnow().replace(days=35)):
            extra_gear.store.is_active = False
            extra_gear.store.save()

            self.assertEqual(utils.invoice_extra_stores(), 0, 'Do not invoice delete stores')

    def test_delete_extra_gear_store_on_plan_limit(self):
        GearBubbleStore.objects.create(
            user=self.user, title="test2", api_token=GEAR_API_TOKEN,
            mode=GEAR_API_MODE)

        extra_gear = self.user.extragearstore_set.first()

        from stripe_subscription import utils
        utils.stripe.InvoiceItem.create = MagicMock(return_value=InvoiceItemMock())

        self.store.is_active = False
        self.store.save()

        self.assertEqual(utils.invoice_extra_stores(), 0, 'Do not invoice delete store')
        self.assertEqual(self.user.extragearstore_set.first().status, 'disabled')

        extra_gear = GearBubbleStore.objects.create(
            user=self.user, title="test3", api_token=GEAR_API_TOKEN,
            mode=GEAR_API_MODE)

        self.assertEqual(utils.invoice_extra_stores(), 1, 'Invoice Extra Gear Store')
        self.assertEqual(self.user.extragearstore_set.first().status, 'disabled')
        self.assertEqual(self.user.extragearstore_set.last().status, 'active')

        import arrow
        with patch.object(utils.arrow, 'utcnow', return_value=arrow.utcnow().replace(days=35)):
            extra_gear.is_active = False
            extra_gear.save()

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
        self.assertEqual(user_count, self.user.profile.get_gear_stores().count())

        self.assertEqual(self.user.extragearstore_set.count(), 0)

        for i in range(10):
            GearBubbleStore.objects.create(
                user=self.user, title="test%s" % i, api_token=GEAR_API_TOKEN,
                mode=GEAR_API_MODE)

        self.assertTrue(self.user.profile.get_gear_stores().count() >= 10)

        self.assertFalse(have_extra_stores(self.user))
        self.assertEqual(self.user.extragearstore_set.count(), 0)

    def test_not_generate_invoice_on_plan_limits_increase(self):
        for i in range(10):
            GearBubbleStore.objects.create(
                user=self.user, title="test%s" % i, api_token=GEAR_API_TOKEN,
                mode=GEAR_API_MODE)
        self.assertTrue(have_extra_stores(self.user))

        from stripe_subscription import utils
        utils.stripe.InvoiceItem.create = MagicMock(return_value=InvoiceItemMock())

        from django.core.cache import cache
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
        import arrow
        with patch.object(utils.arrow, 'utcnow', return_value=arrow.utcnow().replace(days=40)):
            cache.delete('user_extra_stores_ignored_{}'.format(self.user.id))
            cache.delete('user_invoice_checked_{}'.format(self.user.id))
            self.assertEqual(utils.invoice_extra_stores(), 1)
            self.assertEqual(self.user.extragearstore_set.count(), 1)
