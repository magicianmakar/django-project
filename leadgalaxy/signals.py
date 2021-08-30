import arrow
import simplejson as json

from django.dispatch import receiver
from django.dispatch import Signal
from django.conf import settings
from django.core.cache import cache
from django.core.cache.utils import make_template_fragment_key
from django.db.models import Q
from django.db.models.signals import post_save, m2m_changed, post_delete
from django.contrib.auth.signals import user_logged_in
from django.contrib.auth.models import User

from lib.exceptions import capture_exception
from leadgalaxy.models import (
    UserProfile,
    GroupPlan,
    GroupPlanChangeLog,
    ShopifyOrderTrack,
    ShopifyStore,
    ShopifyProduct,
    SubuserPermission,
    SubuserCHQPermission,
    SubuserWooPermission,
    SubuserGearPermission,
    SubuserGKartPermission,
    SubuserBigCommercePermission,
    SUBUSER_STORE_PERMISSIONS,
    SUBUSER_CHQ_STORE_PERMISSIONS,
    SUBUSER_WOO_STORE_PERMISSIONS,
    SUBUSER_GEAR_STORE_PERMISSIONS,
    SUBUSER_GKART_STORE_PERMISSIONS,
    SUBUSER_BIGCOMMERCE_STORE_PERMISSIONS,
)

from addons_core.tasks import cancel_all_addons
from metrics.tasks import activecampaign_update_plan, activecampaign_update_store_count
from profit_dashboard.models import AliexpressFulfillmentCost
from profit_dashboard.utils import get_costs_from_track
from stripe_subscription.stripe_api import stripe
from shopified_core.tasks import keen_send_event
from shopified_core.utils import get_domain
from goals.models import Goal, UserGoalRelationship
from analytic_events.models import LoginEvent, StoreCreatedEvent
from addons_core.models import Addon
from churnzero_core.utils import (
    post_churnzero_addon_update,
    post_churnzero_change_plan_event,
    set_churnzero_account
)


@receiver(post_save, sender=UserProfile)
def update_plan_changed_date(sender, instance, created, **kwargs):
    user = instance.user
    current_plan = instance.plan

    try:
        change_log, created = GroupPlanChangeLog.objects.get_or_create(user=user)
    except:
        return

    try:
        if current_plan and current_plan.is_shopify() and change_log.plan.is_shopify() and current_plan != change_log.plan:
            post_churnzero_change_plan_event(instance.user, current_plan.title)
    except:
        pass

    if current_plan != change_log.plan:
        change_log.previous_plan = change_log.plan
        change_log.plan = current_plan
        change_log.changed_at = arrow.utcnow().datetime
        change_log.save()

        if not current_plan.support_addons or current_plan.is_active_free:
            cancel_all_addons.apply_async([user.id], countdown=5)

        if not settings.DEBUG:
            try:
                activecampaign_update_plan.apply_async([user.id], expires=500)
            except:
                pass

        UserGoalRelationship.objects.filter(user=user).delete()
        for goal in Goal.objects.filter(plans=current_plan):
            UserGoalRelationship.objects.get_or_create(user=user, goal=goal)

    if instance.plan and not instance.has_churnzero_account and not user.is_subuser and not user.is_staff:
        set_churnzero_account(user)


@receiver(post_save, sender=UserProfile)
def invalidate_acp_users(sender, instance, created, **kwargs):
    cache.set('template.cache.acp_users.invalidate', True, timeout=3600)

    if not created and not instance.is_subuser:
        auto_fulfill = instance.get_config_value('auto_shopify_fulfill', 'enable')
        for store_type in ['shopify', 'chq', 'woo', 'bigcommerce']:
            stores = getattr(instance, f'get_{store_type}_stores')()
            stores.update(auto_fulfill=auto_fulfill)


@receiver(post_save, sender=ShopifyOrderTrack)
def invalidate_orders_status(sender, instance, created, **kwargs):
    cache.delete(make_template_fragment_key('orders_status', [instance.store_id]))


@receiver(post_save, sender=User, dispatch_uid="userprofile_creation")
def userprofile_creation(sender, instance, created, **kwargs):
    if created:
        try:
            if getattr(instance, 'no_auto_profile', False):
                return

            if instance.profile:
                return

        except UserProfile.DoesNotExist:
            plan = GroupPlan.objects.filter(default_plan=1).first()
            plan = getattr(instance, 'sub_profile_plan', plan)
            if not plan:
                plan = GroupPlan.objects.create(title='Default Plan', slug='default-plan', default_plan=1)

            # only show order banner to new users.
            config = json.dumps(dict(show_order_banner=True))
            profile = UserProfile.objects.create(user=instance, plan=plan, config=config)

            if plan.is_stripe():
                profile.apply_subscription(plan)

    if not created and instance.have_stripe_billing():
        try:
            customer = instance.stripe_customer
            if customer.data:
                email = json.loads(customer.data).get('email')

                if email != instance.email:
                    cus = stripe.Customer.retrieve(customer.customer_id)
                    cus.email = instance.email

                    customer.stripe_save(cus)
        except:
            capture_exception()


def update_store_count_in_activecampaign(user_id):
    if not settings.DEBUG:
        try:
            activecampaign_update_store_count.apply_async([user_id], expires=500)
        except:
            pass


@receiver(post_save, sender=ShopifyStore)
def add_store_permissions(sender, instance, created, **kwargs):
    if created:
        for codename, name in SUBUSER_STORE_PERMISSIONS:
            SubuserPermission.objects.create(store=instance, codename=codename, name=name)

        update_store_count_in_activecampaign(instance.user.id)


@receiver(m2m_changed, sender=UserProfile.subuser_stores.through)
def add_store_permissions_to_subuser(sender, instance, pk_set, action, **kwargs):
    if action == "post_add":
        stores = ShopifyStore.objects.filter(pk__in=pk_set)
        for store in stores:
            permissions = store.subuser_permissions.all()
            instance.subuser_permissions.add(*permissions)

        update_store_count_in_activecampaign(instance.user.id)


@receiver(m2m_changed, sender=UserProfile.subuser_permissions.through)
def clear_cached_template(sender, instance, pk_set, action, **kwargs):
    permission_pks = SubuserPermission.objects.filter(
        Q(codename='view_help_and_support') | Q(codename='view_bonus_training')
    ).values_list('pk', flat=True)

    if set(permission_pks) & set(pk_set):
        key = make_template_fragment_key('sidebar_link', [instance.user.id, instance.plan_id])
        cache.delete(key)


@receiver(post_save, sender='commercehq_core.CommerceHQStore')
def add_chq_store_permissions(sender, instance, created, **kwargs):
    if created:
        for codename, name in SUBUSER_CHQ_STORE_PERMISSIONS:
            SubuserCHQPermission.objects.create(store=instance, codename=codename, name=name)

        update_store_count_in_activecampaign(instance.user.id)


@receiver(m2m_changed, sender=UserProfile.subuser_chq_stores.through)
def add_chq_store_permissions_to_subuser(sender, instance, pk_set, action, **kwargs):
    if action == "post_add":
        stores = instance.user.models_user.commercehqstore_set.filter(pk__in=pk_set)
        for store in stores:
            permissions = store.subuser_chq_permissions.all()
            instance.subuser_chq_permissions.add(*permissions)

        update_store_count_in_activecampaign(instance.user.id)


@receiver(post_save, sender='woocommerce_core.WooStore')
def add_woo_store_permissions(sender, instance, created, **kwargs):
    if created:
        for codename, name in SUBUSER_WOO_STORE_PERMISSIONS:
            SubuserWooPermission.objects.create(store=instance, codename=codename, name=name)

        update_store_count_in_activecampaign(instance.user.id)


@receiver(m2m_changed, sender=UserProfile.subuser_woo_stores.through)
def add_woo_store_permissions_to_subuser(sender, instance, pk_set, action, **kwargs):
    if action == "post_add":
        stores = instance.user.models_user.woostore_set.filter(pk__in=pk_set)
        for store in stores:
            permissions = store.subuser_woo_permissions.all()
            instance.subuser_woo_permissions.add(*permissions)

        update_store_count_in_activecampaign(instance.user.id)


@receiver(post_save, sender='gearbubble_core.GearBubbleStore')
def add_gear_store_permissions(sender, instance, created, **kwargs):
    if created:
        for codename, name in SUBUSER_GEAR_STORE_PERMISSIONS:
            SubuserGearPermission.objects.create(store=instance, codename=codename, name=name)


@receiver(m2m_changed, sender=UserProfile.subuser_gear_stores.through)
def add_gear_store_permissions_to_subuser(sender, instance, pk_set, action, **kwargs):
    if action == "post_add":
        stores = instance.user.models_user.gearbubblestore_set.filter(pk__in=pk_set)
        for store in stores:
            permissions = store.subuser_gear_permissions.all()
            instance.subuser_gear_permissions.add(*permissions)


@receiver(post_save, sender='groovekart_core.GrooveKartStore')
def add_gkart_store_permissions(sender, instance, created, **kwargs):
    if created:
        for codename, name in SUBUSER_GKART_STORE_PERMISSIONS:
            SubuserGKartPermission.objects.create(store=instance, codename=codename, name=name)

        update_store_count_in_activecampaign(instance.user.id)


@receiver(m2m_changed, sender=UserProfile.subuser_gkart_stores.through)
def add_gkart_store_permissions_to_subuser(sender, instance, pk_set, action, **kwargs):
    if action == "post_add":
        stores = instance.user.models_user.groovekartstore_set.filter(pk__in=pk_set)
        for store in stores:
            permissions = store.subuser_gkart_permissions.all()
            instance.subuser_gkart_permissions.add(*permissions)

        update_store_count_in_activecampaign(instance.user.id)


@receiver(post_save, sender='bigcommerce_core.BigCommerceStore')
def add_bigcommerce_store_permissions(sender, instance, created, **kwargs):
    if created:
        for codename, name in SUBUSER_BIGCOMMERCE_STORE_PERMISSIONS:
            SubuserBigCommercePermission.objects.create(store=instance, codename=codename, name=name)

        update_store_count_in_activecampaign(instance.user.id)


@receiver(m2m_changed, sender=UserProfile.subuser_bigcommerce_stores.through)
def add_bigcommerce_store_permissions_to_subuser(sender, instance, pk_set, action, **kwargs):
    if action == "post_add":
        stores = instance.user.models_user.bigcommercestore_set.filter(pk__in=pk_set)
        for store in stores:
            permissions = store.subuser_bigcommerce_permissions.all()
            instance.subuser_bigcommerce_permissions.add(*permissions)

        update_store_count_in_activecampaign(instance.user.id)


@receiver(post_save, sender=ShopifyOrderTrack, dispatch_uid='sync_aliexpress_fulfillment_cost')
def sync_aliexpress_fulfillment_cost(sender, instance, created, **kwargs):

    try:
        if instance.user.can('profit_dashboard.use'):
            get_costs_from_track(instance, commit=True)
    except User.DoesNotExist:
        pass


@receiver(post_delete, sender=ShopifyOrderTrack, dispatch_uid='delete_aliexpress_fulfillment_cost')
def delete_aliexpress_fulfillment_cost(sender, instance, **kwargs):
    AliexpressFulfillmentCost.objects.filter(
        store_id=instance.store_id,
        order_id=instance.order_id,
        source_id=instance.source_id
    ).delete()


@receiver(post_save, sender=ShopifyProduct)
def shopify_send_keen_event_for_product(sender, instance, created, **kwargs):
    if not settings.DEBUG and settings.KEEN_PROJECT_ID and created:
        try:
            data = json.loads(instance.data)
            source_url = data.get('original_url')
        except:
            source_url = ''

        if instance.store:
            store = instance.store
        else:
            store = instance.user.models_user.profile.get_shopify_stores().first()

        keen_data = {
            'supplier': get_domain(source_url) if source_url else None,
            'source_url': source_url,
            'store': store.title if store else None,
            'store_type': 'Shopify',
            'product_title': instance.title,
            'product_price': instance.price,
            'product_type': instance.product_type,
        }

        keen_send_event.delay('product_save', keen_data)


@receiver(user_logged_in)
def post_login(sender, user, request, **kwargs):
    if user.models_user.profile.has_churnzero_account:
        LoginEvent.objects.create(user=user)


@receiver(m2m_changed, sender=UserProfile.addons.through)
def addons_count_change(sender, instance, pk_set, action, **kwargs):
    models_user = instance.user.models_user
    if models_user.profile.has_churnzero_account and action in ["post_add", "post_remove"]:
        addons = Addon.objects.filter(pk__in=pk_set)
        action = 'added' if action == 'post_add' else 'removed'
        post_churnzero_addon_update(instance.user, addons=addons, action=action)


@receiver(post_save, sender=ShopifyStore)
def store_saved(sender, instance, created, **kwargs):
    if created:
        StoreCreatedEvent.objects.create(user=instance.user, platform='Shopify')


main_subscription_canceled = Signal(providing_args=["stripe_sub"])
main_subscription_updated = Signal(providing_args=["stripe_sub"])
