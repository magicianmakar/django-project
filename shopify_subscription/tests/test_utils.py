import datetime

from decimal import Decimal

from unittest.mock import Mock, PropertyMock, patch

import arrow

from lib.test import BaseTestCase

from leadgalaxy.tests.factories import UserFactory, ShopifyStoreFactory, GroupPlanFactory
from ..utils import (
    ShopifyProfile,
    RecurringSubscription,
    YearlySubscription,
)


class ShopifyProfileTestCase(BaseTestCase):
    @patch('shopify_subscription.utils.ShopifyProfile._get_subscription')
    def test_must_return_true_if_status_is_active(self, _get_subscription):
        _get_subscription.return_value = Mock(is_active=True)
        profile = ShopifyProfile(UserFactory())
        self.assertTrue(profile.is_active)

    @patch('shopify_subscription.utils.ShopifyProfile._get_subscription')
    def test_must_return_correct_date_for_start_date(self, _get_subscription):
        date = '2019-03-24'
        _get_subscription.return_value = Mock(start_date=arrow.get(date))
        profile = ShopifyProfile(UserFactory())
        self.assertEqual(arrow.get(date), profile.start_date)

    @patch('shopify_subscription.utils.ShopifyProfile._get_subscription')
    def test_must_return_correct_date_for_end_date(self, _get_subscription):
        date = '2019-03-24'
        _get_subscription.return_value = Mock(end_date=arrow.get(date))
        profile = ShopifyProfile(UserFactory())
        self.assertEqual(arrow.get(date), profile.end_date)

    @patch('shopify_subscription.utils.ShopifyProfile._get_subscription')
    def test_must_return_correct_date_for_next_renewal_date(self, _get_subscription):
        date = '2019-03-24'
        _get_subscription.return_value = Mock(next_renewal_date=arrow.get(date))
        profile = ShopifyProfile(UserFactory())
        self.assertEqual(arrow.get(date), profile.next_renewal_date)

    @patch('shopify_subscription.utils.ShopifyProfile._get_subscription', Mock())
    def test_must_return_shopify_store(self):
        user = UserFactory()
        store = ShopifyStoreFactory(user=user)
        profile = ShopifyProfile(user)
        self.assertEqual(profile.shopify_store, store)

    @patch('shopify_subscription.utils.ShopifyProfile._get_subscription')
    def test_must_return_correct_total_contract_amount(self, _get_subscription):
        _get_subscription.return_value = Mock(total_contract_amount=Decimal('100.00'))
        profile = ShopifyProfile(UserFactory())
        self.assertEqual(profile.total_contract_amount, Decimal('100.00'))

    @patch('shopify_subscription.utils.ShopifyProfile._get_subscription')
    def test_must_return_true_if_valid(self, _get_subscription):
        _get_subscription.return_value = Mock()
        user = UserFactory()
        store = ShopifyStoreFactory(user=user)
        profile = ShopifyProfile(user)
        property_mock = PropertyMock(return_value=store)
        with patch.object(ShopifyProfile, 'shopify_store', property_mock):
            self.assertTrue(profile.is_valid)

    @patch('shopify_subscription.utils.ShopifyProfile._get_subscription')
    def test_must_have_a_plan_property(self, _get_subscription):
        _get_subscription.return_value = Mock()
        plan = GroupPlanFactory()
        user = UserFactory()
        user.profile.plan = plan
        user.profile.save()
        profile = ShopifyProfile(user)
        self.assertEqual(profile.plan, plan)

    @patch('shopify_subscription.utils.ShopifyProfile._get_application_charges')
    @patch('shopify_subscription.utils.ShopifyProfile._get_subscription')
    def test_must_have_application_charges(self, _get_subscription, _get_application_charges):
        _get_subscription.return_value = Mock()
        profile = ShopifyProfile(UserFactory())
        profile.application_charges
        self.assertTrue(profile._get_application_charges.called)

    @patch('shopify_subscription.utils.ShopifyProfile._get_recurring_charges')
    @patch('shopify_subscription.utils.ShopifyProfile._get_subscription')
    def test_must_have_recurring_charges(self, _get_subscription, _get_recurring_charges):
        _get_subscription.return_value = Mock()
        profile = ShopifyProfile(UserFactory())
        profile.recurring_charges
        self.assertTrue(profile._get_recurring_charges.called)

    @patch('shopify_subscription.utils.ShopifyProfile._get_application_charge_total')
    @patch('shopify_subscription.utils.ShopifyProfile._get_subscription')
    def test_must_have_application_charge_total(self, _get_subscription, _get_application_charge_total):
        _get_subscription.return_value = Mock()
        profile = ShopifyProfile(UserFactory())
        profile.application_charge_total
        self.assertTrue(profile._get_application_charge_total.called)

    def test_must_return_recurring_subscription_for_not_yearly_subscription(self):
        user = UserFactory()
        user.profile.plan = GroupPlanFactory(payment_interval='monthly')
        user.profile.save()
        profile = ShopifyProfile(user)
        subscription = profile._get_subscription()
        self.assertTrue(isinstance(subscription, RecurringSubscription))

    def test_must_return_yearly_subscription_for_yearly_subscription(self):
        user = UserFactory()
        user.profile.plan = GroupPlanFactory(payment_interval='yearly')
        user.profile.save()
        profile = ShopifyProfile(user)
        subscription = profile._get_subscription()
        self.assertTrue(isinstance(subscription, YearlySubscription))

    @patch('shopify_subscription.utils.ShopifyProfile._get_application_charges')
    @patch('shopify_subscription.utils.ShopifyProfile._get_subscription')
    def test_must_return_application_charge_total(self, _get_subscription, _get_application_charges):
        _get_subscription.return_value = Mock()
        application_charge1 = Mock()
        application_charge1.to_dict = Mock(return_value={'price': '11.50'})
        application_charge2 = Mock()
        application_charge2.to_dict = Mock(return_value={'price': '12.50'})
        application_charges = [application_charge1, application_charge2]
        _get_application_charges.return_value = application_charges
        profile = ShopifyProfile(UserFactory())
        profile._get_application_charge_total()
        self.assertTrue(profile._get_application_charge_total(), 24.00)


class RecurringSubscriptionTestCase(BaseTestCase):
    charge = Mock()
    start_date = '2020-04-01'
    billing_on = '2020-05-01'
    balanced_used = 12.50
    charge.to_dict = Mock(return_value={'status': 'active',
                                        'activated_on': start_date,
                                        'billing_on': billing_on,
                                        'balanced_used': balanced_used})

    def test_must_be_associated_with_a_shopify_profile(self):
        profile = Mock()
        subscription = RecurringSubscription(profile)
        self.assertEqual(subscription._profile, profile)

    @patch('shopify_subscription.utils.RecurringSubscription.charge', PropertyMock(return_value=charge))
    def test_must_return_active_if_charge_status_is_active(self):
        profile = Mock()
        subscription = RecurringSubscription(profile)
        self.assertTrue(subscription.is_active)

    @patch('shopify_subscription.utils.RecurringSubscription.charge', PropertyMock(return_value=charge))
    def test_must_return_correct_start_date(self):
        profile = Mock()
        subscription = RecurringSubscription(profile)
        self.assertEqual(subscription.start_date, arrow.get(self.start_date))

    @patch('shopify_subscription.utils.RecurringSubscription.charge', PropertyMock(return_value=charge))
    def test_must_return_correct_renewal_date(self):
        profile = Mock()
        subscription = RecurringSubscription(profile)
        self.assertEqual(subscription.end_date, arrow.get(self.billing_on))

    @patch('shopify_subscription.utils.RecurringSubscription.charge', PropertyMock(return_value=charge))
    def test_must_return_correct_end_date(self):
        profile = Mock()
        subscription = RecurringSubscription(profile)
        end_date = arrow.get(self.start_date).datetime + datetime.timedelta(days=30)
        self.assertEqual(subscription.next_renewal_date, arrow.get(end_date))

    @patch('shopify_subscription.utils.RecurringSubscription.charge', PropertyMock(return_value=charge))
    def test_must_return_correct_balanced_used(self):
        profile = Mock()
        subscription = RecurringSubscription(profile)
        self.assertEqual(subscription.balanced_used, self.balanced_used)

    @patch('shopify_subscription.utils.RecurringSubscription.charge', PropertyMock(return_value=charge))
    def test_must_return_correct_total_contract_amount(self):
        profile = Mock()
        profile.application_charge_total = Decimal('24.50')
        subscription = RecurringSubscription(profile)
        self.assertEqual(subscription.total_contract_amount, 37.00)

    @patch('shopify_subscription.utils.get_active_charge')
    def test_must_get_active_charge(self, get_active_charge):
        profile = Mock()
        subscription = RecurringSubscription(profile)
        subscription.charge
        self.assertTrue(get_active_charge.called)

    def test_must_get_active_charge_from_recurring_charges(self):
        profile = Mock()
        property_mock = PropertyMock(return_value=[])
        type(profile).recurring_charges = property_mock
        subscription = RecurringSubscription(profile)
        subscription.charge
        self.assertTrue(property_mock.called)


class YearlySubscriptionTestCase(BaseTestCase):
    def test_must_return_active_if_charge_status_is_active(self):
        profile = Mock()
        subscription = YearlySubscription(profile)
        charge = Mock()
        charge.to_dict = Mock(return_value={'status': 'active'})
        property_mock = PropertyMock(return_value=charge)
        type(subscription).charge = property_mock
        self.assertTrue(subscription.is_active)

    def test_must_return_active_if_charge_status_is_accepted(self):
        profile = Mock()
        subscription = YearlySubscription(profile)
        charge = Mock()
        charge.to_dict = Mock(return_value={'status': 'accepted'})
        property_mock = PropertyMock(return_value=charge)
        type(subscription).charge = property_mock
        self.assertTrue(subscription.is_active)

    def test_must_return_correct_start_date(self):
        profile = Mock()
        subscription = YearlySubscription(profile)
        charge = Mock()
        created_at = '2020-04-01'
        charge.to_dict = Mock(return_value={'created_at': created_at})
        property_mock = PropertyMock(return_value=charge)
        type(subscription).charge = property_mock
        self.assertEqual(arrow.get(created_at), subscription.start_date)

    def test_must_return_correct_end_date(self):
        profile = Mock()
        subscription = YearlySubscription(profile)
        start_date = arrow.get('2020-04-01')
        property_mock = PropertyMock(return_value=start_date)
        type(subscription).start_date = property_mock
        end_date = start_date.shift(years=1)
        self.assertEqual(end_date, subscription.end_date)

    def test_must_return_correct_next_renewal_date(self):
        profile = Mock()
        subscription = YearlySubscription(profile)
        end_date = arrow.get('2020-04-01')
        property_mock = PropertyMock(return_value=end_date)
        type(subscription).end_date = property_mock
        self.assertEqual(subscription.next_renewal_date, end_date)

    def test_must_have_charge_property(self):
        profile = Mock()
        subscription = YearlySubscription(profile)
        subscription._get_charge = Mock(return_value=Mock())
        subscription.charge
        self.assertTrue(subscription._get_charge.called)

    def test_must_return_correct_contract_amount(self):
        profile = Mock()
        application_charge_total_mock = PropertyMock(return_value=Decimal('11.00'))
        type(profile).application_charge_total = application_charge_total_mock
        subscription = YearlySubscription(profile)
        charge = Mock()
        charge.to_dict = Mock(return_value={'price': '2.00'})
        charge_mock = PropertyMock(return_value=charge)
        type(subscription).charge = charge_mock
        self.assertEqual(subscription._get_total_contract_amount(), 9.00)

    def test_must_return_correct_application_charge(self):
        profile = Mock()
        type(profile).plan = PropertyMock(return_value=Mock(title="Yearly"))
        application_charge1 = Mock()
        application_charge1.status = "active"
        application_charge1.to_dict = Mock(return_value={'name': 'Addon Charge'})
        application_charge2 = Mock()
        application_charge2.status = "active"
        application_charge_name = 'Dropified Yearly for $100'
        application_charge2.to_dict = Mock(return_value={'name': application_charge_name})
        application_charges = [application_charge1, application_charge2]
        application_charges_mock = PropertyMock(return_value=application_charges)
        type(profile).application_charges = application_charges_mock
        subscription = YearlySubscription(profile)
        subscription_charge_name = subscription._get_charge().to_dict().get('name')
        self.assertEqual(subscription_charge_name, application_charge_name)
