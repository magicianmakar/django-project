from unittest.mock import Mock, patch

from arrow import get as arrow_get  # Bypass patched mock

from lib.test import BaseTestCase
from leadgalaxy.tests.factories import ShopifyStoreFactory
from addons_core.utils import (
    sync_stripe_addon,
    sync_stripe_billing,
    create_stripe_subscription,
    update_stripe_subscription,
    create_usage_from_stripe,
    has_shopify_limit_exceeded,
)
from addons_core.models import Addon, AddonPrice
from .factories import (
    AddonUsageFactory,
    StripeProductFactory,
    StripePriceFactory,
    StripeSubscriptionFactory,
    StripeSubscriptionItemFactory,
    RecurringApplicationChargeFactory,
)


def current_date_modifier(today_date):
    def result(*args):
        if args:
            return arrow_get(*args)
        return arrow_get(today_date)
    return result


class AddonTestCase(BaseTestCase):
    def setUp(self):
        with patch('addons_core.tasks.create_or_update_addon_in_stripe.apply_async'), \
                patch('addons_core.tasks.create_or_update_billing_in_stripe.apply_async'), \
                patch('addons_core.tasks.create_subscription_in_stripe.apply_async'), \
                patch('metrics.tasks.activecampaign_update_plan.apply_async'):
            self.addon_usage = AddonUsageFactory()
            self.billing = self.addon_usage.billing
            self.price = self.billing.prices.first()
            self.addon = self.billing.addon
            self.customer_id = self.addon_usage.user.stripe_customer.customer_id
            ShopifyStoreFactory(user=self.addon_usage.user)

    def test_sending_addon_to_stripe(self):
        with patch('stripe.Product.create', return_value=Mock(id='Addon_123')) as stripe_mock:
            sync_stripe_addon(addon=self.addon)

            self.addon.refresh_from_db()
            self.assertEqual(self.addon.stripe_product_id, 'Addon_123')
            stripe_mock.assert_called()

    def test_modify_addon_in_stripe(self):
        with patch('stripe.Product.modify') as stripe_mock:
            self.addon.stripe_product_id = 'Addon_123'
            sync_stripe_addon(addon=self.addon)
            stripe_mock.assert_called()

    def test_saving_addon_from_stripe(self):
        self.addon.delete()
        stripe_product = StripeProductFactory()
        addon = sync_stripe_addon(product=stripe_product)
        self.assertNotEqual(addon, None)
        self.assertEqual(addon.stripe_product_id, stripe_product.id)
        self.assertEqual(addon.title, stripe_product.name)

        stripe_product.name = 'Updated Name'
        with patch('stripe.Price.list', return_value={'data': [1], 'has_more': False}), \
                patch('addons_core.utils.sync_stripe_billing') as mock_sync_billing:
            updated_addon = sync_stripe_addon(product=stripe_product)
            mock_sync_billing.assert_called()

            self.assertNotEqual(updated_addon, None)
            self.assertNotEqual(addon.title, stripe_product.name)
            self.assertEqual(updated_addon.title, stripe_product.name)
            self.assertEqual(Addon.objects.count(), 1)

    def test_sending_price_to_stripe(self):
        with patch('stripe.Plan.create', return_value=Mock(id='AddonPrice_123')) as stripe_mock:
            sync_stripe_billing(addon_price=self.price)

            self.price.refresh_from_db()
            self.assertEqual(self.price.stripe_price_id, 'AddonPrice_123')
            stripe_mock.assert_called()

    def test_modify_price_in_stripe(self):
        with patch('stripe.Price.retrieve',
                   return_value=StripePriceFactory(unit_amount=self.price.price * 100)), \
                patch('stripe.Plan.modify') as stripe_mock, \
                patch('stripe.Plan.create') as stripe_create_mock:
            self.price.stripe_price_id = 'AddonPrice_123'
            sync_stripe_billing(addon_price=self.price)
            stripe_mock.assert_called()
            stripe_create_mock.assert_not_called()

    def test_saving_price_from_stripe(self):
        self.price.delete()
        stripe_price = StripePriceFactory(product=self.addon.stripe_product_id)
        addon_price = sync_stripe_billing(price=stripe_price)
        self.assertNotEqual(addon_price, None)
        self.assertEqual(addon_price.stripe_price_id, stripe_price.id)

        stripe_price.recurring.interval = 'day'
        updated_price = sync_stripe_billing(price=stripe_price)
        self.assertNotEqual(updated_price, None)
        updated_price.billing.refresh_from_db()
        self.assertEqual(updated_price.billing.interval, 0)
        self.assertEqual(AddonPrice.objects.count(), 1)

    def test_creating_stripe_subscription(self):
        today = arrow_get(self.addon_usage.start_at).shift(days=-1)
        with patch('arrow.get', wraps=current_date_modifier(today)):
            item = create_stripe_subscription(self.addon_usage)
            self.assertIsNone(item)

        self.assertTrue(self.addon_usage.start_at == self.addon_usage.next_billing)
        current_billing = self.addon_usage.next_billing
        with patch('arrow.get', wraps=current_date_modifier(self.addon_usage.start_at)), \
                patch('stripe.Subscription.list', return_value={'data': []}), \
                patch('stripe.Subscription.create', return_value=StripeSubscriptionFactory()) as mock_stripe, \
                patch('addons_core.utils.get_customer_subscriptions', return_value=[]):
            item = create_stripe_subscription(self.addon_usage)

            mock_stripe.assert_called()
            self.assertTrue(self.addon_usage.start_at < self.addon_usage.next_billing)
            self.assertNotEqual(self.addon_usage.next_billing, current_billing)

        self.addon_usage.next_billing = current_billing
        self.addon_usage.stripe_subscription_id = ''
        self.addon_usage.stripe_subscription_item_id = ''
        self.addon_usage.save()
        subscription = StripeSubscriptionFactory(
            current_period_start=current_billing,
            items={'data': [StripeSubscriptionItemFactory()]}
        )
        with patch('addons_core.utils.get_customer_subscriptions', return_value=[subscription]), \
                patch('stripe.Subscription.list', return_value={'data': []}), \
                patch('stripe.SubscriptionItem.create',
                      return_value=StripeSubscriptionItemFactory()) as mock_stripe:
            item = create_stripe_subscription(self.addon_usage)

            mock_stripe.assert_called()
            self.assertTrue(self.addon_usage.start_at < self.addon_usage.next_billing)
            self.assertNotEqual(self.addon_usage.next_billing, current_billing)

    def test_update_stripe_subscription(self):
        subscription = StripeSubscriptionFactory()
        item = subscription['items']['data'][0]
        new_item = StripeSubscriptionItemFactory()

        with patch('stripe.Subscription.retrieve', return_value=subscription), \
                patch('stripe.SubscriptionItem.create', return_value=new_item), \
                patch('stripe.SubscriptionItem.delete') as mock_stripe:
            self.addon_usage.stripe_subscription_item_id = item.id
            item = update_stripe_subscription(self.addon_usage)

            self.assertEqual(self.addon_usage.stripe_subscription_item_id, new_item.id)
            mock_stripe.assert_called()

    def test_create_usage_from_stripe(self):
        item = StripeSubscriptionItemFactory(
            price=StripePriceFactory(id=self.price.stripe_price_id),
            subscription='123'
        )

        with patch('stripe.Subscription.retrieve',
                   return_value=StripeSubscriptionFactory(customer=self.customer_id)):
            addon_usage = create_usage_from_stripe(item)
            self.assertNotEqual(addon_usage, None)

    def test_shopify_must_exceed_limit(self):
        charge = RecurringApplicationChargeFactory()
        charge.customize = Mock(return_value=True)

        exceeded = has_shopify_limit_exceeded(self.addon_usage.user, self.billing, charge)
        charge.customize.assert_called_once()
        self.assertTrue(exceeded)

    def test_shopify_must_not_exceed_limit(self):
        charge = RecurringApplicationChargeFactory()
        charge.customize = Mock(return_value=True)
        charge.capped_amount += self.price.price

        exceeded = has_shopify_limit_exceeded(self.addon_usage.user, self.billing, charge)
        charge.customize.assert_not_called()
        self.assertFalse(exceeded)

    def test_must_not_have_shopify_recurring_charge(self):
        target = 'shopify.resources.recurring_application_charge.RecurringApplicationCharge.find'
        charge = RecurringApplicationChargeFactory()
        charge.status = 'declined'
        with patch(target, return_value=[charge]), \
                self.assertRaises(Exception) as context:
            has_shopify_limit_exceeded(self.addon_usage.user)

        self.assertIn('Not Found', str(context.exception))
