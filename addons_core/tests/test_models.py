from decimal import Decimal
from unittest.mock import patch, Mock

import arrow
from arrow import get as arrow_get  # Bypass patched mock

from lib.test import BaseTestCase
from .factories import AddonUsageFactory


def today_wrapper(today_date):
    def result(*args):
        if args:
            return arrow_get(*args)
        return arrow_get(today_date)
    return result


class AddonBillingTestCase(BaseTestCase):
    def setUp(self):
        created_at = arrow.get('2020-01-10').datetime
        self.monthly_price = Decimal('29.99')
        with patch('django.utils.timezone.now', Mock(return_value=created_at)):
            self.addon_usage = AddonUsageFactory(addon__monthly_price=self.monthly_price)

    def test_billing_first_charge(self):
        with patch('arrow.get', wraps=today_wrapper('2020-01-30')):
            before_subscription = arrow.get('2020-01-05')
            charge = self.addon_usage.usage_charge(before_subscription)
            self.assertEqual(charge, Decimal('19.35'))

            after_subscription = arrow.get('2020-01-12')
            charge = self.addon_usage.usage_charge(after_subscription)
            self.assertEqual(charge, Decimal('17.41'))

    def test_recurring_subscription(self):
        with patch('arrow.get', wraps=today_wrapper('2020-02-20')):
            outside_billing_cycle = arrow.get('2020-01-19')
            charge = self.addon_usage.usage_charge(outside_billing_cycle)
            self.assertEqual(charge, Decimal('31.99'))

        with patch('arrow.get', wraps=today_wrapper('2020-02-20')):
            last_billed_at = arrow.get('2020-01-20')
            charge = self.addon_usage.usage_charge(last_billed_at)
            self.assertEqual(charge, self.monthly_price)

    def test_cancelled_subscription(self):
        self.addon_usage.cancelled_at = arrow.get('2020-02-10')
        with patch('arrow.get', wraps=today_wrapper('2020-02-20')):
            last_billed_at = arrow.get('2020-01-20')
            charge = self.addon_usage.usage_charge(last_billed_at)
            self.assertEqual(charge, Decimal('20.32'))
