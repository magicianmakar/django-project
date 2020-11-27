from unittest.mock import Mock, patch

import arrow

from lib.test import BaseTestCase
from addons_core.models import AddonUsage
from .factories import AddonUsageFactory


class AddonModelsTestCase(BaseTestCase):
    def setUp(self):
        with patch('addons_core.tasks.create_or_update_addon_in_stripe.apply_async'), \
                patch('addons_core.tasks.create_or_update_billing_in_stripe.apply_async'), \
                patch('addons_core.tasks.create_subscription_in_stripe.apply_async'), \
                patch('metrics.tasks.activecampaign_update_plan.apply_async'):

            self.addon_usages = []

            created_at = arrow.get().replace(days=5).datetime
            with patch('django.utils.timezone.now', Mock(return_value=created_at)):
                self.first_addon_usage = AddonUsageFactory()
                self.addon_usages.append(self.first_addon_usage)

            created_at = arrow.get().replace(days=4).datetime
            with patch('django.utils.timezone.now', Mock(return_value=created_at)):
                self.addon_usages.append(AddonUsageFactory())

            created_at = arrow.get().replace(days=3).datetime
            with patch('django.utils.timezone.now', Mock(return_value=created_at)):
                self.addon_usages.append(AddonUsageFactory())

            created_at = arrow.get().replace(days=2).datetime
            with patch('django.utils.timezone.now', Mock(return_value=created_at)):
                self.addon_usages.append(AddonUsageFactory())

            created_at = arrow.get().replace(days=1).datetime
            with patch('django.utils.timezone.now', Mock(return_value=created_at)):
                self.last_addon_usage = AddonUsageFactory()
                self.addon_usages.append(self.last_addon_usage)

    def test_addon_usage_required_sort(self):
        self.assertTrue(AddonUsage.objects.first().id, self.first_addon_usage.id)
        self.assertTrue(AddonUsage.objects.last().id, self.last_addon_usage.id)
