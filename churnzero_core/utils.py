import copy

from django.conf import settings

from shopified_core.tasks import requests_async


# Create your views here.
def post_churnzero_product_import(user, description, source):
    return post_churnzero_actions(actions=[{
        'appKey': settings.CHURNZERO_APP_KEY,
        'accountExternalId': user.models_user.username,
        'contactExternalId': user.username,
        'accountExternalIdHash': user.profile.churnzero_account_id_hash,
        'contactExternalIdHash': user.profile.churnzero_contact_id_hash,
        'action': 'trackEvent',
        'eventName': 'Import Product',
        'description': description,
        'cf_Source': source,
    }])


def post_churnzero_product_export(user, description):
    return post_churnzero_actions(actions=[{
        'appKey': settings.CHURNZERO_APP_KEY,
        'accountExternalId': user.models_user.username,
        'contactExternalId': user.username,
        'accountExternalIdHash': user.profile.churnzero_account_id_hash,
        'contactExternalIdHash': user.profile.churnzero_contact_id_hash,
        'action': 'trackEvent',
        'eventName': 'Send Product to Store',
        'description': description,
    }])


def post_churnzero_addon_update(user, addons, action):
    params = {
        'appKey': settings.CHURNZERO_APP_KEY,
        'accountExternalId': user.models_user.username,
        'contactExternalId': user.username,
        'accountExternalIdHash': user.profile.churnzero_account_id_hash,
        'contactExternalIdHash': user.profile.churnzero_contact_id_hash,
        'action': 'trackEvent',
    }
    actions = []
    if action == 'added':
        for addon in addons:
            action = copy.copy(params)
            action['eventName'] = 'Installed Addon'
            action['description'] = f"{addon.title} ({addon.addon_hash})"
            actions.append(action)
    if action == 'removed':
        for addon in addons:
            action = copy.copy(params)
            action['eventName'] = 'Uninstalled Addon'
            action['description'] = f"{addon.title} ({addon.addon_hash})"
            actions.append(action)

    return post_churnzero_actions(actions=actions)


def post_churnzero_actions(actions):
    if settings.CHURNZERO_APP_KEY and not settings.DEBUG:
        requests_async.apply_async(
            kwargs={
                'url': 'https://analytics.churnzero.net/i',
                'method': 'post',
                'json': actions
            })
