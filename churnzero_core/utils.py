import copy

from django.conf import settings
from django.utils.functional import cached_property

from shopified_core.tasks import requests_async
from shopify_subscription.utils import ShopifyProfile


class SetAccountActionBuilder:
    def __init__(self, user):
        self._models_user = user.models_user
        self._profile = self._models_user.profile
        self._plan = self._profile.plan
        self._action = self.get_required_attributes()

    @cached_property
    def is_stripe_user(self):
        return self._plan.is_stripe() and hasattr(self._models_user, "stripe_customer")

    @cached_property
    def is_shopify_user(self):
        return bool(self._plan.is_shopify() and self.shopify_profile)

    @cached_property
    def shopify_profile(self):
        shopify_profile = ShopifyProfile(self._models_user)

        return shopify_profile if shopify_profile.is_valid else None

    def get_required_attributes(self):
        return dict(
            action='setAttribute',
            entity='account',
            appKey=settings.CHURNZERO_APP_KEY,
            accountExternalId=self._models_user.username,
            contactExternalId=self._models_user.username,
            accountExternalIdHash=self._profile.churnzero_account_id_hash,
            contactExternalIdHash=self._profile.churnzero_contact_id_hash,
        )

    def add_name(self):
        name_elements = [self._models_user.first_name, self._models_user.last_name]
        name = ' '.join(name_elements).strip()
        self._action['attr_Name'] = name if name else "(no name)"

    def add_stripe_customer_id(self):
        self._action['attr_Stripe_customer_id'] = self._models_user.stripe_customer.customer_id

    def add_gateway(self):
        if self.is_stripe_user:
            self._action['attr_Gateway'] = 'Stripe'
        if self.is_shopify_user:
            self._action['attr_Gateway'] = 'Shopify'

    def add_installed_addons(self):
        addons_list = self._profile.addons.values_list('churnzero_name', flat=True)
        self._action['attr_Installed Addons'] = ', '.join(addons_list)

    def add_shopify_stores_count(self):
        self._action['attr_Shopify Stores Count'] = self._profile.get_shopify_stores().count()

    def add_woo_stores_count(self):
        self._action['attr_WooCommerce Stores Count'] = self._profile.get_woo_stores().count()

    def add_chq_stores_count(self):
        self._action['attr_CommerceHQ Stores Count'] = self._profile.get_chq_stores().count()

    def add_gear_stores_count(self):
        self._action['attr_GearBubble Stores Count'] = self._profile.get_gear_stores().count()

    def add_gkart_stores_count(self):
        self._action['attr_GrooveKart Stores Count'] = self._profile.get_gkart_stores().count()

    def add_bigcommerce_stores_count(self):
        self._action['attr_BigCommerce Stores Count'] = self._profile.get_bigcommerce_stores().count()

    def add_next_renewal_date(self):
        self._action['attr_NextRenewalDate'] = self.shopify_profile.next_renewal_date.isoformat()

    def add_start_date(self):
        self._action['attr_StartDate'] = self.shopify_profile.start_date.isoformat()

    def add_end_date(self):
        self._action['attr_EndDate'] = self.shopify_profile.end_date.isoformat()

    def add_total_contract_amount(self):
        self._action['attr_TotalContractAmount'] = float(self.shopify_profile.total_contract_amount)

    def add_is_active(self):
        self._action['attr_IsActive'] = self.shopify_profile.is_active

    def get_action(self):
        return self._action

    def get_complete_action(self):
        self.add_name()
        self.add_gateway()
        self.add_installed_addons()
        self.add_shopify_stores_count()
        self.add_woo_stores_count()
        self.add_chq_stores_count()
        self.add_gear_stores_count()
        self.add_gkart_stores_count()
        self.add_bigcommerce_stores_count()

        if self.is_stripe_user:
            self.add_stripe_customer_id()

        if self.is_shopify_user:
            self.add_is_active()
            self.add_total_contract_amount()
            if self.shopify_profile.start_date:
                self.add_start_date()
            if self.shopify_profile.end_date:
                self.add_end_date()
            if self.shopify_profile.next_renewal_date:
                self.add_next_renewal_date()

        return self._action


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


def set_churnzero_account(models_user):
    action_builder = SetAccountActionBuilder(models_user)
    if action_builder.is_shopify_user or action_builder.is_stripe_user:
        action = action_builder.get_complete_action()
        post_churnzero_actions([action])
        models_user.profile.has_churnzero_account = True
        models_user.profile.save()
