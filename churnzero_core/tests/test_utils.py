from unittest.mock import patch, Mock

from django.conf import settings
from django.test.utils import override_settings

from addons_core.tests.factories import AddonFactory
from churnzero_core.utils import post_churnzero_product_import, post_churnzero_product_export, post_churnzero_addon_update
from leadgalaxy import utils
from leadgalaxy.tests.factories import UserFactory, GroupPlanFactory
from lib.test import BaseTestCase
from stripe_subscription.tests.factories import StripePlanFactory, StripeCustomerFactory


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
    @override_settings(DEBUG=False)
    @override_settings(CHURNZERO_APP_KEY='test')
    @patch('stripe_subscription.models.stripe')
    @patch('shopified_core.tasks.requests_async.apply_async')
    def test_must_submit_with_correct_parameters(self, post_request, stripe):
        models_user = UserFactory(username='modelsuser')
        user = UserFactory()
        user.profile.subuser_parent = models_user
        user.profile.save()
        stripe.Plan = Mock()
        plan = GroupPlanFactory(payment_gateway='stripe')
        stripe.Plan.retrieve = Mock(return_value=plan)
        user.models_user.profile.plan = plan
        user.models_user.profile.plan.is_stripe = Mock(return_value=True)
        user.models_user.profile.plan.stripe_plan = StripePlanFactory(stripe_id='abc')
        user.models_user.stripe_customer = StripeCustomerFactory(customer_id='abc')
        addon1 = AddonFactory(title='test1')
        addon2 = AddonFactory(title='test2')
        user.models_user.profile.addons.add(addon1, addon2)

        utils.set_churnzero_account(user.models_user)

        actions = [{
            'appKey': settings.CHURNZERO_APP_KEY,
            'accountExternalId': 'modelsuser',
            'contactExternalId': 'modelsuser',
            'accountExternalIdHash': user.models_user.profile.churnzero_account_id_hash,
            'contactExternalIdHash': user.models_user.profile.churnzero_contact_id_hash,
            'action': 'setAttribute',
            'entity': 'account',
            'attr_Stripe_customer_id': 'abc',
            'attr_Gateway': 'Stripe',
            'attr_Installed Addons': 'test1, test2',
        }]

        post_request.assert_called_with(kwargs=dict(url="https://analytics.churnzero.net/i", method="post", json=actions))

    @override_settings(DEBUG=False)
    @override_settings(CHURNZERO_APP_KEY='test')
    @patch('stripe_subscription.models.stripe')
    @patch('shopified_core.tasks.requests_async.apply_async')
    def test_must_update_users_has_churnzero_account_property(self, post_request, stripe):
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
        utils.set_churnzero_account(user.models_user, create=True)
        user.models_user.profile.refresh_from_db()
        self.assertTrue(user.models_user.profile.has_churnzero_account)
