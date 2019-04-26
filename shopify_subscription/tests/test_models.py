from unittest.mock import patch, Mock, PropertyMock

import datetime

import arrow

from django.utils import timezone

from lib.test import BaseTestCase

from shopify_subscription.tests import factories as f


class ShopifySubscriptionTestCase(BaseTestCase):
    def test_returns_true_if_current_subscription_is_on_trial(self):
        target = 'shopify_subscription.models.ShopifySubscription.subscription'
        with patch(target, new_callable=PropertyMock) as subscription:
            now = timezone.now()
            tomorrow = now + datetime.timedelta(days=1)
            trial_ends_on = arrow.get(tomorrow).format('YYYY-MM-DD')
            subscription.return_value = {'trial_ends_on': trial_ends_on}
            shopify_subscription = f.ShopifySubscriptionFactory()
            shopify_subscription.refresh = Mock(return_value=None)
            self.assertTrue(shopify_subscription.on_trial)

    def test_returns_false_if_current_subscription_has_no_trial_ends_on_value(self):
        target = 'shopify_subscription.models.ShopifySubscription.subscription'
        with patch(target, new_callable=PropertyMock) as subscription:
            subscription.return_value = {'trial_ends_on': None}
            shopify_subscription = f.ShopifySubscriptionFactory()
            shopify_subscription.refresh = Mock(return_value=None)
            self.assertFalse(shopify_subscription.on_trial)

    def test_returns_false_if_current_subscription_has_ended(self):
        target = 'shopify_subscription.models.ShopifySubscription.subscription'
        with patch(target, new_callable=PropertyMock) as subscription:
            now = timezone.now()
            yesterday = now - datetime.timedelta(days=1)
            trial_ends_on = arrow.get(yesterday).format('YYYY-MM-DD')
            subscription.return_value = {'trial_ends_on': trial_ends_on}
            shopify_subscription = f.ShopifySubscriptionFactory()
            shopify_subscription.refresh = Mock(return_value=None)
            self.assertFalse(shopify_subscription.on_trial)

    def test_returns_trial_days_left(self):
        target = 'shopify_subscription.models.ShopifySubscription.subscription'
        with patch(target, new_callable=PropertyMock) as subscription:
            trial_days_left = 5
            now = timezone.now().date()
            trial_ends_on = now + datetime.timedelta(days=trial_days_left)
            trial_ends_on = arrow.get(trial_ends_on).format('YYYY-MM-DD')
            subscription.return_value = {'trial_ends_on': trial_ends_on}
            shopify_subscription = f.ShopifySubscriptionFactory()
            shopify_subscription.refresh = Mock(return_value=None)
            self.assertEquals(shopify_subscription.trial_days_left, trial_days_left)
