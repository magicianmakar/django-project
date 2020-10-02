from decimal import Decimal
from unittest.mock import Mock, patch

import arrow
from django.test import override_settings

from lib.test import BaseTestCase
from .factories import AddonUsageFactory


class AddonAPITestCase(BaseTestCase):
    def setUp(self):
        self.addon_usage = AddonUsageFactory(addon__monthly_price=Decimal('29.99'))
        self.addon = self.addon_usage.addon
        self.user = self.addon_usage.user
        self.client.force_login(self.user)

    def test_install_addon_multiple_times(self):
        self.assertEqual(self.user.addonusage_set.count(), 1)
        self.client.post('/api/addons/install', {'addon': self.addon.id})
        self.assertEqual(self.user.addonusage_set.count(), 1)

    def test_install_addon_after_cancellation(self):
        self.assertEqual(self.user.addonusage_set.count(), 1)
        self.client.post('/api/addons/uninstall', {'addon': self.addon.id})

        created_at = arrow.get().replace(days=1).datetime
        with patch('django.utils.timezone.now', Mock(return_value=created_at)):
            self.client.post('/api/addons/install', {'addon': self.addon.id})
            self.assertEqual(self.user.addonusage_set.count(), 2)

    @override_settings(SESSION_COOKIE_AGE=31536000)
    def test_purchase_addon_multiple_times_with_trial(self):
        self.client.force_login(self.user)
        self.addon.trial_period_days = 15
        self.addon.save()

        self.client.post('/api/addons/uninstall', {'addon': self.addon.id})
        self.addon_usage.delete()

        # Burning through 10 days of trial
        created_at = arrow.get('2020-01-10').datetime
        with patch('django.utils.timezone.now', Mock(return_value=created_at)):
            self.client.post('/api/addons/install', {'addon': self.addon.id})

        created_at = arrow.get('2020-01-20').datetime
        with patch('django.utils.timezone.now', Mock(return_value=created_at)):
            self.client.post('/api/addons/uninstall', {'addon': self.addon.id})

        self.assertEqual(self.user.addonusage_set.count(), 1)
        addon_usage = self.user.addonusage_set.first()
        self.assertEqual(addon_usage.get_latest_charge()[2], Decimal('0'))

        # Burning through remaining 5 days of trial and being charged for another 5
        created_at = arrow.get('2020-03-10').datetime
        with patch('django.utils.timezone.now', Mock(return_value=created_at)):
            self.client.post('/api/addons/install', {'addon': self.addon.id})

        created_at = arrow.get('2020-03-20').datetime
        with patch('django.utils.timezone.now', Mock(return_value=created_at)):
            self.client.post('/api/addons/uninstall', {'addon': self.addon.id})

        self.assertEqual(self.user.addonusage_set.count(), 2)
        addon_usage = self.user.addonusage_set.first()
        self.assertEqual(addon_usage.get_latest_charge()[2], Decimal('4.84'))
