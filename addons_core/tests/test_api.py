from unittest.mock import Mock, patch

import arrow
from django.test import override_settings

from lib.test import BaseTestCase
from .factories import AddonUsageFactory


class AddonAPITestCase(BaseTestCase):
    def setUp(self):
        with patch('addons_core.tasks.create_or_update_addon_in_stripe.apply_async'), \
                patch('addons_core.tasks.create_or_update_billing_in_stripe.apply_async'), \
                patch('addons_core.tasks.create_subscription_in_stripe.apply_async'), \
                patch('metrics.tasks.activecampaign_update_plan.apply_async'):
            self.addon_usage = AddonUsageFactory()
            self.billing = self.addon_usage.billing
            self.price = self.billing.prices.first()
            self.addon = self.billing.addon
            self.user = self.addon_usage.user

        self.client.force_login(self.user)

    def test_install_addon_multiple_times(self):
        self.assertEqual(self.user.addonusage_set.count(), 1)
        self.client.post('/api/addons/install', {'billing': self.billing.id})
        self.assertEqual(self.user.addonusage_set.count(), 1)

    def test_install_addon_after_cancellation(self):
        self.assertEqual(self.user.addonusage_set.count(), 1)
        self.client.post('/api/addons/uninstall', {'addon': self.addon.id})

        created_at = arrow.get().replace(days=1).datetime
        with patch('django.utils.timezone.now', Mock(return_value=created_at)), \
                patch('addons_core.tasks.create_subscription_in_stripe.apply_async'):
            self.client.post('/api/addons/install', {'billing': self.billing.id})
            self.assertEqual(self.user.addonusage_set.count(), 2)

    @override_settings(SESSION_COOKIE_AGE=31536000)
    def test_purchase_addon_multiple_times_with_trial(self):
        self.client.force_login(self.user)
        self.billing.trial_period_days = 15
        self.billing.save()

        self.client.post('/api/addons/uninstall', {'addon': self.addon.id})
        self.addon_usage.delete()

        # Burning through 10 days of trial
        created_at = arrow.get('2020-01-10').datetime
        with patch('django.utils.timezone.now', Mock(return_value=created_at)), \
                patch('addons_core.tasks.create_subscription_in_stripe.apply_async'):
            self.client.post('/api/addons/install', {'billing': self.billing.id})

        created_at = arrow.get('2020-01-20').datetime
        with patch('django.utils.timezone.now', Mock(return_value=created_at)):
            self.client.post('/api/addons/uninstall', {'addon': self.addon.id})

        self.assertEqual(self.user.addonusage_set.count(), 1)
        addon_usage = self.user.addonusage_set.first()
        self.assertEqual(addon_usage.get_trial_days_left(created_at), 5)

        # Burning through remaining 5 days of trial and being charged
        created_at = arrow.get('2020-03-10')
        with patch('django.utils.timezone.now', Mock(return_value=created_at.datetime)), \
                patch('addons_core.tasks.create_subscription_in_stripe.apply_async'):
            self.client.post('/api/addons/install', {'billing': self.billing.id})

        usages = self.user.addonusage_set.all()
        self.assertEqual(len(usages), 2)
        self.assertEqual(usages[0].start_at, created_at.shift(days=5).date())
        self.assertEqual(usages[0].next_price.price, self.price.price)
