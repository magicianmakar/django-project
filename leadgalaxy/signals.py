import arrow
import simplejson as json

from django.dispatch import receiver
from django.dispatch import Signal
from django.core.cache import cache
from django.core.cache.utils import make_template_fragment_key
from django.db.models import Q
from django.db.models.signals import post_save, m2m_changed, post_delete
from django.contrib.auth.models import User

from leadgalaxy.models import (
    UserProfile,
    GroupPlan,
    GroupPlanChangeLog,
    ShopifyOrderTrack,
    ShopifyStore,
    SubuserPermission,
    SubuserCHQPermission,
    SubuserWooPermission,
    SubuserGearPermission,
    SubuserGKartPermission,
    SUBUSER_STORE_PERMISSIONS,
    SUBUSER_CHQ_STORE_PERMISSIONS,
    SUBUSER_WOO_STORE_PERMISSIONS,
    SUBUSER_GEAR_STORE_PERMISSIONS,
    SUBUSER_GKART_STORE_PERMISSIONS,
)

from profit_dashboard.models import AliexpressFulfillmentCost
from profit_dashboard.utils import get_costs_from_track
from stripe_subscription.stripe_api import stripe
from goals.models import Goal, UserGoalRelationship


@receiver(post_save, sender=UserProfile)
def update_plan_changed_date(sender, instance, created, **kwargs):
    user = instance.user
    current_plan = instance.plan

    try:
        change_log, created = GroupPlanChangeLog.objects.get_or_create(user=user)
    except:
        return

    if current_plan != change_log.plan:
        change_log.previous_plan = change_log.plan
        change_log.plan = current_plan
        change_log.changed_at = arrow.utcnow().datetime
        change_log.save()


@receiver(post_save, sender=UserProfile)
def invalidate_acp_users(sender, instance, created, **kwargs):
    cache.set('template.cache.acp_users.invalidate', True, timeout=3600)

    if not created and not instance.is_subuser:
        instance.get_shopify_stores().update(auto_fulfill=instance.get_config_value('auto_shopify_fulfill', ''))
        instance.get_chq_stores().update(auto_fulfill=instance.get_config_value('auto_shopify_fulfill', ''))


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
            if not plan:
                plan = GroupPlan.objects.create(title='Default Plan', slug='default-plan', default_plan=1)

            profile = UserProfile.objects.create(user=instance, plan=plan)

            if plan.is_stripe():
                profile.apply_subscription(plan)

    if not created and instance.have_stripe_billing():
        try:
            customer = instance.stripe_customer
            email = json.loads(customer.data).get('email')

            if email != instance.email:
                cus = stripe.Customer.retrieve(customer.customer_id)
                cus.email = instance.email

                customer.stripe_save(cus)
        except:
            from raven.contrib.django.raven_compat.models import client as raven_client
            raven_client.captureException()


@receiver(post_save, sender=ShopifyStore)
def add_store_permissions(sender, instance, created, **kwargs):
    if created:
        for codename, name in SUBUSER_STORE_PERMISSIONS:
            SubuserPermission.objects.create(store=instance, codename=codename, name=name)


@receiver(m2m_changed, sender=UserProfile.subuser_stores.through)
def add_store_permissions_to_subuser(sender, instance, pk_set, action, **kwargs):
    if action == "post_add":
        stores = ShopifyStore.objects.filter(pk__in=pk_set)
        for store in stores:
            permissions = store.subuser_permissions.all()
            instance.subuser_permissions.add(*permissions)


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


@receiver(m2m_changed, sender=UserProfile.subuser_chq_stores.through)
def add_chq_store_permissions_to_subuser(sender, instance, pk_set, action, **kwargs):
    if action == "post_add":
        stores = instance.user.models_user.commercehqstore_set.filter(pk__in=pk_set)
        for store in stores:
            permissions = store.subuser_chq_permissions.all()
            instance.subuser_chq_permissions.add(*permissions)


@receiver(post_save, sender='woocommerce_core.WooStore')
def add_woo_store_permissions(sender, instance, created, **kwargs):
    if created:
        for codename, name in SUBUSER_WOO_STORE_PERMISSIONS:
            SubuserWooPermission.objects.create(store=instance, codename=codename, name=name)


@receiver(m2m_changed, sender=UserProfile.subuser_woo_stores.through)
def add_woo_store_permissions_to_subuser(sender, instance, pk_set, action, **kwargs):
    if action == "post_add":
        stores = instance.user.models_user.woostore_set.filter(pk__in=pk_set)
        for store in stores:
            permissions = store.subuser_woo_permissions.all()
            instance.subuser_woo_permissions.add(*permissions)


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


@receiver(m2m_changed, sender=UserProfile.subuser_gkart_stores.through)
def add_gkart_store_permissions_to_subuser(sender, instance, pk_set, action, **kwargs):
    if action == "post_add":
        stores = instance.user.models_user.groovekartstore_set.filter(pk__in=pk_set)
        for store in stores:
            permissions = store.subuser_gkart_permissions.all()
            instance.subuser_gkart_permissions.add(*permissions)


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


@receiver(post_save, sender=User)
def add_goals_to_new_user(sender, instance, created, **kwargs):
    if created:
        for goal in Goal.objects.all():
            UserGoalRelationship.objects.create(user=instance, goal=goal)


main_subscription_canceled = Signal(providing_args=["stripe_sub"])
main_subscription_updated = Signal(providing_args=["stripe_sub"])
