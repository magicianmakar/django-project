from decimal import Decimal
from unittest.mock import patch, Mock, PropertyMock

import arrow

from django.conf import settings
from django.test.utils import override_settings
from django.core.cache import cache

from addons_core.tests.factories import AddonFactory
from leadgalaxy.tests.factories import UserFactory, GroupPlanFactory, ShopifyStoreFactory
from woocommerce_core.tests.factories import WooStoreFactory
from commercehq_core.tests.factories import CommerceHQStoreFactory
from gearbubble_core.tests.factories import GearBubbleStoreFactory
from groovekart_core.tests.factories import GrooveKartStoreFactory
from bigcommerce_core.tests.factories import BigCommerceStoreFactory

from lib.test import BaseTestCase
from stripe_subscription.tests.factories import StripePlanFactory, StripeCustomerFactory

from churnzero_core.utils import (
    post_churnzero_product_import,
    post_churnzero_product_export,
    post_churnzero_addon_update,
    set_churnzero_account,
    SetAccountActionBuilder,
    post_churnzero_cancellation_event,
)


class PostChurnZeroProductImportTestCase(BaseTestCase):
    @override_settings(DEBUG=False)
    @override_settings(CHURNZERO_APP_KEY='test')
    @patch('shopified_core.tasks.requests_async.apply_async')
    def test_must_be_called_with_correct_credentials(self, post_request):
        models_user = UserFactory(username='modelsuser')
        user = UserFactory(username='user')
        user.profile.subuser_parent = models_user
        user.profile.save()

        post_churnzero_product_import(user, 'description', 'source')

        actions = [{
            'appKey': settings.CHURNZERO_APP_KEY,
            'accountExternalId': 'modelsuser',
            'contactExternalId': 'user',
            'accountExternalIdHash': user.profile.churnzero_account_id_hash,
            'contactExternalIdHash': user.profile.churnzero_contact_id_hash,
            'action': 'trackEvent',
            'eventName': 'Import Product',
            'description': 'description',
            'cf_Source': 'source',
        }]

        post_request.assert_called_with(kwargs=dict(url="https://analytics.churnzero.net/i", method="post", json=actions))


class PostChurnZeroProductExportTestCase(BaseTestCase):
    @override_settings(DEBUG=False)
    @override_settings(CHURNZERO_APP_KEY='test')
    @patch('shopified_core.tasks.requests_async.apply_async')
    def test_must_be_called_with_correct_credentials(self, post_request):
        models_user = UserFactory(username='modelsuser')
        user = UserFactory(username='user')
        user.profile.subuser_parent = models_user
        user.profile.save()

        post_churnzero_product_export(user, 'description')

        actions = [{
            'appKey': settings.CHURNZERO_APP_KEY,
            'accountExternalId': 'modelsuser',
            'contactExternalId': 'user',
            'accountExternalIdHash': user.profile.churnzero_account_id_hash,
            'contactExternalIdHash': user.profile.churnzero_contact_id_hash,
            'action': 'trackEvent',
            'eventName': 'Send Product to Store',
            'description': 'description',
        }]

        post_request.assert_called_with(kwargs=dict(url="https://analytics.churnzero.net/i", method="post", json=actions))


class PostChurnZeroAddonUpdateTestCase(BaseTestCase):
    @override_settings(DEBUG=False)
    @override_settings(CHURNZERO_APP_KEY='test')
    @patch('shopified_core.tasks.requests_async.apply_async')
    def test_must_be_called_with_correct_credentials_when_adding(self, post_request):
        models_user = UserFactory(username='modelsuser')
        user = UserFactory(username='user')
        user.profile.subuser_parent = models_user
        user.profile.save()
        addons = [AddonFactory(title='a', addon_hash="#!"), AddonFactory(title='b', addon_hash="$%")]

        post_churnzero_addon_update(user, addons=addons, action="added")

        actions = [{
            'appKey': settings.CHURNZERO_APP_KEY,
            'accountExternalId': 'modelsuser',
            'contactExternalId': 'user',
            'accountExternalIdHash': user.profile.churnzero_account_id_hash,
            'contactExternalIdHash': user.profile.churnzero_contact_id_hash,
            'action': 'trackEvent',
            'eventName': 'Installed Addon',
            'description': 'a (#!)',
        }, {
            'appKey': settings.CHURNZERO_APP_KEY,
            'accountExternalId': 'modelsuser',
            'contactExternalId': 'user',
            'accountExternalIdHash': user.profile.churnzero_account_id_hash,
            'contactExternalIdHash': user.profile.churnzero_contact_id_hash,
            'action': 'trackEvent',
            'eventName': 'Installed Addon',
            'description': 'b ($%)',
        }]

        post_request.assert_called_with(kwargs=dict(url="https://analytics.churnzero.net/i", method="post", json=actions))

    @override_settings(DEBUG=False)
    @override_settings(CHURNZERO_APP_KEY='test')
    @patch('shopified_core.tasks.requests_async.apply_async')
    def test_must_be_called_with_correct_credentials_when_removing(self, post_request):
        models_user = UserFactory(username='modelsuser')
        user = UserFactory(username='user')
        user.profile.subuser_parent = models_user
        user.profile.save()
        addons = [AddonFactory(title='a', addon_hash="#!"), AddonFactory(title='b', addon_hash="$%")]

        post_churnzero_addon_update(user, addons=addons, action="removed")

        actions = [{
            'appKey': settings.CHURNZERO_APP_KEY,
            'accountExternalId': 'modelsuser',
            'contactExternalId': 'user',
            'accountExternalIdHash': user.profile.churnzero_account_id_hash,
            'contactExternalIdHash': user.profile.churnzero_contact_id_hash,
            'action': 'trackEvent',
            'eventName': 'Uninstalled Addon',
            'description': 'a (#!)',
        }, {
            'appKey': settings.CHURNZERO_APP_KEY,
            'accountExternalId': 'modelsuser',
            'contactExternalId': 'user',
            'accountExternalIdHash': user.profile.churnzero_account_id_hash,
            'contactExternalIdHash': user.profile.churnzero_contact_id_hash,
            'action': 'trackEvent',
            'eventName': 'Uninstalled Addon',
            'description': 'b ($%)',
        }]

        post_request.assert_called_with(kwargs=dict(url="https://analytics.churnzero.net/i", method="post", json=actions))


class SetChurnZeroAccountTestCase(BaseTestCase):
    def setUp(self):
        cache.clear()

    def tearDown(self):
        cache.clear()

    @override_settings(DEBUG=False)
    @override_settings(CHURNZERO_APP_KEY='test')
    @patch('stripe_subscription.models.stripe')
    @patch('shopified_core.tasks.requests_async.apply_async')
    def test_must_submit_with_correct_parameters_for_stripe_user(self, post_request, stripe):
        models_user = UserFactory(username='modelsuser', email='test@email.com')
        user = UserFactory()
        user.profile.subuser_parent = models_user
        user.profile.save()
        stripe.Plan = Mock()
        plan = GroupPlanFactory(payment_gateway='stripe', title='Test Plan', free_plan=False)
        stripe.Plan.retrieve = Mock(return_value=plan)
        user.models_user.profile.plan = plan
        user.models_user.profile.plan.is_stripe = Mock(return_value=True)
        user.models_user.profile.plan.stripe_plan = StripePlanFactory(stripe_id='abc')
        user.models_user.stripe_customer = StripeCustomerFactory(customer_id='abc')
        type(user.models_user.stripe_customer).is_active = PropertyMock(return_value=True)
        addon1 = AddonFactory(title='test1')
        addon2 = AddonFactory(title='test2')
        user.models_user.profile.addons.add(addon1, addon2)
        addons_list = user.models_user.profile.addons.values_list('churnzero_name', flat=True)
        ShopifyStoreFactory(user=models_user)
        WooStoreFactory(user=models_user)
        CommerceHQStoreFactory(user=models_user)
        GearBubbleStoreFactory(user=models_user)
        GrooveKartStoreFactory(user=models_user)
        BigCommerceStoreFactory(user=models_user)
        set_churnzero_account(user.models_user)

        actions = [{
            'appKey': settings.CHURNZERO_APP_KEY,
            'accountExternalId': 'modelsuser',
            'contactExternalId': 'modelsuser',
            'accountExternalIdHash': user.models_user.profile.churnzero_account_id_hash,
            'contactExternalIdHash': user.models_user.profile.churnzero_contact_id_hash,
            'action': 'setAttribute',
            'entity': 'account',
            'attr_Name': models_user.email,
            'attr_Stripe_customer_id': 'abc',
            'attr_Gateway': 'Stripe',
            'attr_Installed Addons': ', '.join(addons_list),
            'attr_Plan': plan.title,
            'attr_Shopify Stores Count': 1,
            'attr_WooCommerce Stores Count': 1,
            'attr_CommerceHQ Stores Count': 1,
            'attr_GearBubble Stores Count': 1,
            'attr_GrooveKart Stores Count': 1,
            'attr_BigCommerce Stores Count': 1,
            'attr_IsActive': True
        }]

        post_request.assert_called_with(kwargs=dict(url="https://analytics.churnzero.net/i", method="post", json=actions))

    @override_settings(DEBUG=False)
    @override_settings(CHURNZERO_APP_KEY='test')
    @patch('churnzero_core.utils.ShopifyProfile.is_valid', PropertyMock(return_value=True))
    @patch('churnzero_core.utils.ShopifyProfile.next_renewal_date', PropertyMock(return_value=arrow.get('2012-04-01')))
    @patch('churnzero_core.utils.ShopifyProfile.start_date', PropertyMock(return_value=arrow.get('2012-03-01')))
    @patch('churnzero_core.utils.ShopifyProfile.end_date', PropertyMock(return_value=arrow.get('2012-03-01')))
    @patch('churnzero_core.utils.ShopifyProfile.total_contract_amount', PropertyMock(return_value=Decimal('100.00')))
    @patch('churnzero_core.utils.ShopifyProfile.is_active', PropertyMock(return_value=True))
    @patch('shopified_core.tasks.requests_async.apply_async')
    def test_must_submit_with_correct_parameters_for_shopify_user(self, post_request):
        models_user = UserFactory(username='modelsuser', email='test@email.com')
        user = UserFactory()
        user.profile.subuser_parent = models_user
        user.profile.save()
        plan = GroupPlanFactory(payment_gateway='shopify')
        user.models_user.profile.plan = plan
        user.models_user.profile.plan.is_shopify = Mock(return_value=True)
        addon1 = AddonFactory(title='test1')
        addon2 = AddonFactory(title='test2')
        user.models_user.profile.addons.add(addon1, addon2)
        addons_list = user.models_user.profile.addons.values_list('churnzero_name', flat=True)
        ShopifyStoreFactory(user=models_user)
        WooStoreFactory(user=models_user)
        CommerceHQStoreFactory(user=models_user)
        GearBubbleStoreFactory(user=models_user)
        GrooveKartStoreFactory(user=models_user)
        BigCommerceStoreFactory(user=models_user)
        set_churnzero_account(user.models_user)

        actions = [{
            'appKey': settings.CHURNZERO_APP_KEY,
            'accountExternalId': 'modelsuser',
            'contactExternalId': 'modelsuser',
            'accountExternalIdHash': user.models_user.profile.churnzero_account_id_hash,
            'contactExternalIdHash': user.models_user.profile.churnzero_contact_id_hash,
            'action': 'setAttribute',
            'entity': 'account',
            'attr_Name': models_user.email,
            'attr_IsActive': True,
            # Custom attributes
            'attr_Gateway': models_user.profile.plan.payment_gateway.title(),
            'attr_Installed Addons': ', '.join(addons_list),
            'attr_Plan': plan.title,
            'attr_Shopify Stores Count': 1,
            'attr_WooCommerce Stores Count': 1,
            'attr_CommerceHQ Stores Count': 1,
            'attr_GearBubble Stores Count': 1,
            'attr_GrooveKart Stores Count': 1,
            'attr_BigCommerce Stores Count': 1,
        }]

        post_request.assert_called_with(kwargs=dict(url="https://analytics.churnzero.net/i", method="post", json=actions))

    @override_settings(DEBUG=False)
    @override_settings(CHURNZERO_APP_KEY='test')
    @patch('churnzero_core.utils.ShopifyProfile.is_valid', PropertyMock(return_value=True))
    @patch('churnzero_core.utils.ShopifyProfile.next_renewal_date', PropertyMock(return_value=arrow.get('2012-04-01')))
    @patch('churnzero_core.utils.ShopifyProfile.start_date', PropertyMock(return_value=arrow.get('2012-03-01')))
    @patch('churnzero_core.utils.ShopifyProfile.end_date', PropertyMock(return_value=arrow.get('2012-03-01')))
    @patch('churnzero_core.utils.ShopifyProfile.total_contract_amount', PropertyMock(return_value=Decimal('100.00')))
    @patch('churnzero_core.utils.ShopifyProfile.is_active', PropertyMock(return_value=True))
    @patch('shopified_core.tasks.requests_async.apply_async')
    def test_must_not_submit_if_user_is_neither_stripe_nor_shopify(self, post_request):
        models_user = UserFactory(username='modelsuser', email='test@email.com')
        user = UserFactory()
        user.profile.subuser_parent = models_user
        user.profile.save()
        plan = GroupPlanFactory(payment_gateway='')
        user.models_user.profile.plan = plan
        user.models_user.profile.plan.is_shopify = Mock(return_value=False)
        user.models_user.profile.plan.is_stripe = Mock(return_value=False)
        addon1 = AddonFactory(title='test1')
        addon2 = AddonFactory(title='test2')
        user.models_user.profile.addons.add(addon1, addon2)
        ShopifyStoreFactory(user=models_user)
        WooStoreFactory(user=models_user)
        CommerceHQStoreFactory(user=models_user)
        GearBubbleStoreFactory(user=models_user)
        GrooveKartStoreFactory(user=models_user)
        BigCommerceStoreFactory(user=models_user)
        set_churnzero_account(user.models_user)
        self.assertFalse(post_request.called)

    @override_settings(DEBUG=False)
    @override_settings(CHURNZERO_APP_KEY='test')
    @patch('stripe_subscription.models.stripe')
    @patch('shopified_core.tasks.requests_async.apply_async')
    def test_must_update_users_has_churnzero_account_property_of_stripe_user(self, post_request, stripe):
        post_request.return_value = Mock()
        user = UserFactory()
        user.profile.has_churnzero_account = False
        user.profile.save()
        stripe.Plan = Mock()
        plan = GroupPlanFactory(payment_gateway='stripe')
        stripe.Plan.retrieve = Mock(return_value=plan)
        user.models_user.profile.plan = plan
        user.models_user.profile.plan.is_stripe = Mock(return_value=True)
        user.models_user.profile.plan.stripe_plan = StripePlanFactory(stripe_id='abc')
        user.models_user.stripe_customer = StripeCustomerFactory(customer_id='abc')
        set_churnzero_account(user.models_user)
        user.models_user.profile.refresh_from_db()
        self.assertTrue(user.models_user.profile.has_churnzero_account)

    @override_settings(DEBUG=False)
    @override_settings(CHURNZERO_APP_KEY='test')
    @patch('churnzero_core.utils.ShopifyProfile.is_valid', PropertyMock(return_value=True))
    @patch('churnzero_core.utils.ShopifyProfile.next_renewal_date', PropertyMock(return_value=arrow.get('2012-04-01')))
    @patch('churnzero_core.utils.ShopifyProfile.start_date', PropertyMock(return_value=arrow.get('2012-03-01')))
    @patch('churnzero_core.utils.ShopifyProfile.end_date', PropertyMock(return_value=arrow.get('2012-03-01')))
    @patch('churnzero_core.utils.ShopifyProfile.total_contract_amount', PropertyMock(return_value=Decimal('100.00')))
    @patch('churnzero_core.utils.ShopifyProfile.is_active', PropertyMock(return_value=True))
    @patch('shopified_core.tasks.requests_async.apply_async')
    def test_must_update_users_has_churnzero_account_property_of_shopify_user(self, post_request):
        post_request.return_value = Mock()
        user = UserFactory()
        user.profile.has_churnzero_account = False
        user.profile.save()
        plan = GroupPlanFactory(payment_gateway='shopify')
        user.models_user.profile.plan = plan
        user.models_user.profile.plan.is_shopify = Mock(return_value=True)
        set_churnzero_account(user.models_user)
        user.models_user.profile.refresh_from_db()
        self.assertTrue(user.models_user.profile.has_churnzero_account)

    @override_settings(DEBUG=False)
    @override_settings(CHURNZERO_APP_KEY='test')
    @patch('churnzero_core.utils.ShopifyProfile.is_valid', PropertyMock(return_value=True))
    @patch('churnzero_core.utils.ShopifyProfile.next_renewal_date', PropertyMock(return_value=arrow.get('2012-04-01')))
    @patch('churnzero_core.utils.ShopifyProfile.start_date', PropertyMock(return_value=arrow.get('2012-03-01')))
    @patch('churnzero_core.utils.ShopifyProfile.end_date', PropertyMock(return_value=arrow.get('2012-03-01')))
    @patch('churnzero_core.utils.ShopifyProfile.total_contract_amount', PropertyMock(return_value=Decimal('100.00')))
    @patch('churnzero_core.utils.ShopifyProfile.is_active', PropertyMock(return_value=True))
    @patch('shopified_core.tasks.requests_async.apply_async')
    def test_must_not_update_users_has_churnzero_account_property_if_neither_shopify_nor_stripe_user(self, post_request):
        post_request.return_value = Mock()
        user = UserFactory()
        user.profile.has_churnzero_account = False
        user.profile.save()
        plan = GroupPlanFactory(payment_gateway='')
        user.models_user.profile.plan = plan
        user.models_user.profile.plan.is_shopify = Mock(return_value=False)
        user.models_user.profile.plan.is_stripe = Mock(return_value=False)
        set_churnzero_account(user.models_user)
        user.models_user.profile.refresh_from_db()
        self.assertFalse(user.models_user.profile.has_churnzero_account)


class SetAccountActionBuilderTestCase(BaseTestCase):
    def test_must_add_user_email_as_name_attribute(self):
        email = 'modelsuser@test.com'
        models_user = UserFactory(email=email)
        user = UserFactory()
        user.profile.subuser_parent = models_user
        user.profile.save()
        builder = SetAccountActionBuilder(user)
        builder.add_name()
        action = builder.get_action()
        self.assertEqual(action['attr_Name'], email)

    def test_must_add_store_name_as_name_attribute_if_no_email(self):
        models_user = UserFactory(email='')
        title = 'The Store'
        ShopifyStoreFactory(user=models_user, title=title)
        user = UserFactory()
        user.profile.subuser_parent = models_user
        user.profile.save()
        builder = SetAccountActionBuilder(user)
        builder.add_name()
        action = builder.get_action()
        self.assertEqual(action['attr_Name'], title)

    def test_must_add_user_first_name_and_last_name_as_name_attribute_if_no_email_or_store_name(self):
        models_user = UserFactory(email='', first_name="Models", last_name="User")
        user = UserFactory()
        user.profile.subuser_parent = models_user
        user.profile.save()
        builder = SetAccountActionBuilder(user)
        builder.add_name()
        action = builder.get_action()
        self.assertEqual(action['attr_Name'], "Models User")

    def test_must_add_username_as_name_attribute_as_last_fallback(self):
        models_user = UserFactory(email="", username='modelsuser', first_name="", last_name="")
        user = UserFactory()
        user.profile.subuser_parent = models_user
        user.profile.save()
        builder = SetAccountActionBuilder(user)
        builder.add_name()
        action = builder.get_action()
        self.assertEqual(action['attr_Name'], "modelsuser")

    def test_must_add_group_plan_name(self):
        models_user = UserFactory()
        user = UserFactory()
        user.profile.subuser_parent = models_user
        user.profile.save()
        title = 'Test Plan'
        plan = GroupPlanFactory(payment_gateway='stripe', title=title)
        user.models_user.profile.plan = plan
        user.models_user.profile.save()
        builder = SetAccountActionBuilder(user)
        builder.add_plan()
        action = builder.get_action()
        self.assertEqual(action['attr_Plan'], title)


class PostChurnZeroCancellationEventTestCase(BaseTestCase):
    @override_settings(DEBUG=False)
    @override_settings(CHURNZERO_APP_KEY='test')
    @patch('shopified_core.tasks.requests_async.apply_async')
    def test_must_be_called_with_correct_credentials_cancelling(self, post_request):
        user = UserFactory(first_name="John", last_name="Doe", username='username')
        post_churnzero_cancellation_event(user)
        actions = [{
            'appKey': settings.CHURNZERO_APP_KEY,
            'accountExternalId': 'username',
            'contactExternalId': 'username',
            'accountExternalIdHash': user.profile.churnzero_account_id_hash,
            'contactExternalIdHash': user.profile.churnzero_contact_id_hash,
            'action': 'trackEvent',
            'eventName': 'Cancellation',
            'description': "John Doe",
        }, {
            'appKey': settings.CHURNZERO_APP_KEY,
            'accountExternalId': 'username',
            'contactExternalId': 'username',
            'accountExternalIdHash': user.profile.churnzero_account_id_hash,
            'contactExternalIdHash': user.profile.churnzero_contact_id_hash,
            'action': 'setAttribute',
            'entity': 'account',
            'attr_IsActive': False
        }]
        post_request.assert_called_with(kwargs=dict(url="https://analytics.churnzero.net/i", method="post", json=actions))

    @override_settings(DEBUG=False)
    @override_settings(CHURNZERO_APP_KEY='test')
    @patch('shopified_core.tasks.requests_async.apply_async')
    def test_must_be_called_with_username_and_not_full_name_when_cancelling(self, post_request):
        user = UserFactory(username='username', first_name='', last_name='')
        post_churnzero_cancellation_event(user)
        actions = [{
            'appKey': settings.CHURNZERO_APP_KEY,
            'accountExternalId': 'username',
            'contactExternalId': 'username',
            'accountExternalIdHash': user.profile.churnzero_account_id_hash,
            'contactExternalIdHash': user.profile.churnzero_contact_id_hash,
            'action': 'trackEvent',
            'eventName': 'Cancellation',
            'description': 'username',
        }, {
            'appKey': settings.CHURNZERO_APP_KEY,
            'accountExternalId': 'username',
            'contactExternalId': 'username',
            'accountExternalIdHash': user.profile.churnzero_account_id_hash,
            'contactExternalIdHash': user.profile.churnzero_contact_id_hash,
            'action': 'setAttribute',
            'entity': 'account',
            'attr_IsActive': False
        }]
        post_request.assert_called_with(kwargs=dict(url="https://analytics.churnzero.net/i", method="post", json=actions))
