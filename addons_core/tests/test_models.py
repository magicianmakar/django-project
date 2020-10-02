from decimal import Decimal
from unittest.mock import Mock, patch

import arrow
from arrow import get as arrow_get  # Bypass patched mock

from lib.test import BaseTestCase
from .factories import AddonUsageFactory


def current_date_modifier(today_date):
    def result(*args):
        if args:
            return arrow_get(*args)
        return arrow_get(today_date)
    return result


class AddonUsageTestCase(BaseTestCase):
    def setUp(self):
        self.monthly_price = Decimal('29.99')
        created_at = '2020-01-10'
        with patch('django.utils.timezone.now', Mock(return_value=arrow.get(created_at).datetime)), \
                patch('arrow.get', wraps=current_date_modifier(created_at)):
            self.addon_usage = AddonUsageFactory(
                addon__monthly_price=self.monthly_price,
                user__stripesubscription__period_start=arrow.get('2020-01-05').datetime,
            )
            self.addon = self.addon_usage.addon
            self.user = self.addon_usage.user

            self.assertEqual(self.addon_usage.billing_day, 5)
            self.billing_day = str(self.addon_usage.billing_day).zfill(2)

    def test_billing_first_charges(self):
        with patch('arrow.get', wraps=current_date_modifier(f'2020-02-{self.billing_day}')):
            start, end, charge = self.addon_usage.get_latest_charge()
            self.assertEqual(charge, Decimal('29.99'))

        created_at = '2020-05-04'
        with patch('django.utils.timezone.now', Mock(return_value=arrow.get(created_at).datetime)), \
                patch('arrow.get', wraps=current_date_modifier(created_at)):
            addon_usage = AddonUsageFactory(addon__monthly_price=Decimal('9.99'), user=self.user)

        charged_at = '2020-05-05'
        with patch('arrow.get', wraps=current_date_modifier(charged_at)):
            start, end, charge = addon_usage.get_latest_charge()
            self.assertEqual(charge, Decimal('9.99'))
            self.assertEqual(addon_usage.billed_to, arrow.get(created_at).shift(months=1).datetime)

    def test_recurring_subscriptions(self):
        with patch('arrow.get', wraps=current_date_modifier(f'2020-02-{self.billing_day}')):
            start, end, charge = self.addon_usage.get_latest_charge()
            self.assertEqual(charge, self.monthly_price)
            self.assertEqual(self.addon_usage.billed_to, arrow.get('2020-02-10').datetime)

        created_at = '2020-01-21'
        with patch('django.utils.timezone.now', Mock(return_value=arrow.get(created_at).datetime)), \
                patch('arrow.get', wraps=current_date_modifier(created_at)):
            monthly_price = Decimal('9.99')
            addon_usage = AddonUsageFactory(addon__monthly_price=monthly_price, user=self.user)

        billing_day = str(addon_usage.billing_day).zfill(2)
        today = f'2020-03-{billing_day}'
        with patch('arrow.get', wraps=current_date_modifier(today)):
            start, end, charge = addon_usage.get_latest_charge()
            self.assertEqual(charge, monthly_price * 2)
            self.assertEqual(addon_usage.billed_to, arrow.get('2020-03-21').datetime)

        today = f'2020-04-{billing_day}'
        with patch('arrow.get', wraps=current_date_modifier(today)):
            start, end, charge = addon_usage.get_latest_charge()
            self.assertEqual(charge, monthly_price)
            self.assertEqual(addon_usage.billed_to, arrow.get('2020-04-21').datetime)

    def test_cancelled_subscription_cost(self):
        with patch('arrow.get', wraps=current_date_modifier(f'2020-05-{self.billing_day}')):
            self.addon_usage.get_latest_charge()
            self.assertEqual(self.addon_usage.billed_to, arrow.get('2020-05-10').datetime)

        self.addon_usage.cancelled_at = arrow.get('2020-05-11').datetime
        self.addon_usage.save()
        with patch('arrow.get', wraps=current_date_modifier(f'2020-06-{self.billing_day}')):
            start, end, charge = self.addon_usage.get_latest_charge()
            self.assertEqual(charge, Decimal('0.97'))

        self.addon_usage.cancelled_at = arrow.get('2020-06-09').datetime
        self.addon_usage.save()
        with patch('arrow.get', wraps=current_date_modifier(f'2020-07-{self.billing_day}')):
            start, end, charge = self.addon_usage.get_latest_charge()
            self.assertEqual(charge, Decimal('-0.97'))

        # Try billing after cancelation
        with patch('arrow.get', wraps=current_date_modifier(f'2020-09-{self.billing_day}')):
            start, end, charge = self.addon_usage.get_latest_charge()
            self.assertEqual(charge, Decimal('0.00'))

        # Missing billing for several months
        self.addon_usage.cancelled_at = arrow.get('2020-02-09').datetime
        self.addon_usage.billed_to = None
        self.addon_usage.save()
        with patch('arrow.get', wraps=current_date_modifier(f'2020-06-{self.billing_day}')):
            start, end, charge = self.addon_usage.get_latest_charge()
            self.assertEqual(charge, Decimal('-0.97'))

    def test_charge_after_trial(self):
        created_at = '2020-02-01'
        with patch('django.utils.timezone.now', Mock(return_value=arrow.get(created_at).datetime)), \
                patch('arrow.get', wraps=current_date_modifier(created_at)):
            first_addon_usage = AddonUsageFactory(
                addon__monthly_price=Decimal('9.99'),
                addon__trial_period_days=15,
                user__stripesubscription__period_start=arrow.get('2020-01-01').datetime,
            )
            billing_day = str(first_addon_usage.billing_day).zfill(2)
            self.assertEqual(first_addon_usage.billed_to, None)

        with patch('arrow.get', wraps=current_date_modifier(f'2020-02-{billing_day}')):
            start, end, charge = first_addon_usage.get_latest_charge()
            self.assertEqual(charge, Decimal('0.00'))
            self.assertEqual(first_addon_usage.billed_to, None)

        with patch('arrow.get', wraps=current_date_modifier(f'2020-03-{billing_day}')):
            start, end, charge = first_addon_usage.get_latest_charge()
            self.assertEqual(charge, Decimal('9.99'))
            self.assertEqual(first_addon_usage.billed_to, arrow.get(f'2020-03-{first_addon_usage.interval_day}').datetime)

        created_at = '2020-04-16'
        with patch('django.utils.timezone.now', Mock(return_value=arrow.get(created_at).datetime)), \
                patch('arrow.get', wraps=current_date_modifier(created_at)):
            addon_usage = AddonUsageFactory(
                addon__monthly_price=Decimal('10.00'),
                addon__trial_period_days=15,
                user=first_addon_usage.user,
            )

        after_trial = arrow.get(created_at).shift(days=14).format('YYYY-MM-DD')
        with patch('arrow.get', wraps=current_date_modifier(after_trial)):
            start, end, charge = addon_usage.get_latest_charge()
            self.assertEqual(charge, Decimal('0.00'))

        with patch('arrow.get', wraps=current_date_modifier('2020-05-02')):
            start, end, charge = addon_usage.get_latest_charge()
            self.assertEqual(charge, Decimal('10.00'))
            self.assertEqual(addon_usage.billed_to, arrow.get(f'2020-06-{addon_usage.interval_day}').datetime)

        created_at = '2020-04-25'
        with patch('django.utils.timezone.now', Mock(return_value=arrow.get(created_at).datetime)), \
                patch('arrow.get', wraps=current_date_modifier(created_at)):
            addon_usage = AddonUsageFactory(
                addon__monthly_price=Decimal('10.00'),
                addon__trial_period_days=15,
                user=first_addon_usage.user,
            )

        with patch('arrow.get', wraps=current_date_modifier('2020-05-09')):
            start, end, charge = addon_usage.get_latest_charge()
            self.assertEqual(charge, Decimal('0.00'))

        created_at = '2020-04-17'
        with patch('django.utils.timezone.now', Mock(return_value=arrow.get(created_at).datetime)), \
                patch('arrow.get', wraps=current_date_modifier(created_at)):
            addon_usage = AddonUsageFactory(
                addon__monthly_price=Decimal('10.00'),
                addon__trial_period_days=5,
                user=first_addon_usage.user,
            )
            billing_day = str(addon_usage.billing_day).zfill(2)

        with patch('arrow.get', wraps=current_date_modifier(f'2020-05-{billing_day}')):
            start, end, charge = addon_usage.get_latest_charge()
            self.assertEqual(charge, Decimal('10.00'))
            self.assertEqual(addon_usage.billed_to, arrow.get('2020-05-22').datetime)
