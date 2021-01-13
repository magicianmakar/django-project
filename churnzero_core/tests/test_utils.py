from unittest.mock import patch

from django.conf import settings

from addons_core.tests.factories import AddonFactory
from churnzero_core.utils import post_churnzero_product_import, post_churnzero_product_export, post_churnzero_addon_update
from leadgalaxy.tests.factories import UserFactory
from lib.test import BaseTestCase


class PostChurnZeroProductImportTestCase(BaseTestCase):
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
