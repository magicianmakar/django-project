import arrow
import simplejson as json

from django.conf import settings
from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.cache.utils import make_template_fragment_key
from django.db.models import Q
from django.db.models.signals import m2m_changed, post_delete, post_save, pre_delete, pre_save
from django.dispatch import Signal, receiver

from addons_core.tasks import cancel_all_addons
from goals.models import Goal, UserGoalRelationship
from leadgalaxy.models import (
    SUBUSER_BIGCOMMERCE_STORE_PERMISSIONS,
    SUBUSER_CHQ_STORE_PERMISSIONS,
    SUBUSER_EBAY_STORE_PERMISSIONS,
    SUBUSER_FB_STORE_PERMISSIONS,
    SUBUSER_GEAR_STORE_PERMISSIONS,
    SUBUSER_GKART_STORE_PERMISSIONS,
    SUBUSER_STORE_PERMISSIONS,
    SUBUSER_WOO_STORE_PERMISSIONS,
    SUBUSER_GOOGLE_STORE_PERMISSIONS,
    GroupPlan,
    GroupPlanChangeLog,
    ShopifyOrderTrack,
    ShopifyProduct,
    ShopifyStore,
    SubuserBigCommercePermission,
    SubuserCHQPermission,
    SubuserEbayPermission,
    SubuserFBPermission,
    SubuserGearPermission,
    SubuserGKartPermission,
    SubuserPermission,
    SubuserWooPermission,
    SubuserGooglePermission,
    UserProfile
)
from leadgalaxy.utils import deactivate_suredone_account, activate_suredone_account
from lib.exceptions import capture_exception
from profit_dashboard.models import AliexpressFulfillmentCost
from profit_dashboard.utils import get_costs_from_track
from stripe_subscription.stripe_api import stripe
from shopified_core.tasks import keen_send_event
from shopified_core.utils import get_domain
from suredone_core.utils import SureDoneUtils


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

        if not current_plan.support_addons or current_plan.is_active_free:
            cancel_all_addons.apply_async([user.id], countdown=5)

        UserGoalRelationship.objects.filter(user=user).delete()
        for goal in Goal.objects.filter(plans=current_plan):
            UserGoalRelationship.objects.get_or_create(user=user, goal=goal)

        sd_account = SureDoneUtils(user).get_sd_account(user, None, filter_active=False)
        if sd_account:
            sd_perm = False
            for channel in settings.SUREDONE_CHANNELS:
                if user.can(f'{channel}.use'):
                    sd_perm = True
                    break

            if sd_perm:
                activate_suredone_account(sd_account)
            else:
                deactivate_suredone_account(sd_account)


@receiver(post_save, sender=UserProfile)
def invalidate_acp_users(sender, instance, created, **kwargs):
    cache.set('template.cache.acp_users.invalidate', True, timeout=3600)

    if not created and not instance.is_subuser:
        auto_fulfill = instance.get_config_value('auto_shopify_fulfill', 'enable')
        for store_type in ['shopify', 'chq', 'woo', 'bigcommerce', 'ebay', 'fb', 'google']:
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


@receiver(post_save, sender='bigcommerce_core.BigCommerceStore')
def add_bigcommerce_store_permissions(sender, instance, created, **kwargs):
    if created:
        for codename, name in SUBUSER_BIGCOMMERCE_STORE_PERMISSIONS:
            SubuserBigCommercePermission.objects.create(store=instance, codename=codename, name=name)


@receiver(m2m_changed, sender=UserProfile.subuser_bigcommerce_stores.through)
def add_bigcommerce_store_permissions_to_subuser(sender, instance, pk_set, action, **kwargs):
    if action == "post_add":
        stores = instance.user.models_user.bigcommercestore_set.filter(pk__in=pk_set)
        for store in stores:
            permissions = store.subuser_bigcommerce_permissions.all()
            instance.subuser_bigcommerce_permissions.add(*permissions)


def add_ebay_store_permissions_base(store):
    for codename, name in SUBUSER_EBAY_STORE_PERMISSIONS:
        SubuserEbayPermission.objects.create(store=store, codename=codename, name=name)


@receiver(post_save, sender='ebay_core.EbayStore')
def add_ebay_store_permissions(sender, instance, created, **kwargs):
    if created:
        add_ebay_store_permissions_base(instance)


@receiver(m2m_changed, sender=UserProfile.subuser_ebay_stores.through)
def add_ebay_store_permissions_to_subuser(sender, instance, pk_set, action, **kwargs):
    if action == "post_add":
        stores = instance.user.models_user.ebaystore_set.filter(pk__in=pk_set)
        for store in stores:
            permissions = store.subuser_ebay_permissions.all()
            instance.subuser_ebay_permissions.add(*permissions)


def add_fb_store_permissions_base(store):
    for codename, name in SUBUSER_FB_STORE_PERMISSIONS:
        SubuserFBPermission.objects.create(store=store, codename=codename, name=name)


@receiver(post_save, sender='facebook_core.FBStore')
def add_fb_store_permissions(sender, instance, created, **kwargs):
    if created:
        add_fb_store_permissions_base(instance)


@receiver(m2m_changed, sender=UserProfile.subuser_fb_stores.through)
def add_fb_store_permissions_to_subuser(sender, instance, pk_set, action, **kwargs):
    if action == "post_add":
        stores = instance.user.models_user.fbstore_set.filter(pk__in=pk_set)
        for store in stores:
            permissions = store.subuser_fb_permissions.all()
            instance.subuser_fb_permissions.add(*permissions)


def add_google_store_permissions_base(store):
    for codename, name in SUBUSER_GOOGLE_STORE_PERMISSIONS:
        SubuserGooglePermission.objects.create(store=store, codename=codename, name=name)


@receiver(post_save, sender='google_core.GoogleStore')
def add_google_store_permissions(sender, instance, created, **kwargs):
    if created:
        add_google_store_permissions_base(instance)


@receiver(m2m_changed, sender=UserProfile.subuser_google_stores.through)
def add_google_store_permissions_to_subuser(sender, instance, pk_set, action, **kwargs):
    if action == "post_add":
        stores = instance.user.models_user.googlestore_set.filter(pk__in=pk_set)
        for store in stores:
            permissions = store.subuser_google_permissions.all()
            instance.subuser_google_permissions.add(*permissions)


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
            'store_id': store.id if store else 0,
            'user_id': instance.user_id,
            'product_title': instance.title,
            'product_price': instance.price,
            'product_type': instance.product_type,
        }

        keen_send_event.delay('product_save', keen_data)


@receiver(pre_delete, sender=User)
def deactivate_sd_account_on_user_delete(sender, instance, **kwargs):
    sd_account = SureDoneUtils(instance).get_sd_account(instance, None, filter_active=False)
    if sd_account:
        deactivate_suredone_account(sd_account)


@receiver(pre_save, sender=User)
def change_sd_account_status_on_user_save(sender, instance, **kwargs):
    user = User.objects.filter(pk=instance.pk)
    if user:
        user = user.first()
        sd_account = SureDoneUtils(instance).get_sd_account(instance, None, filter_active=False)
        if sd_account:
            if not instance.is_active and user.is_active:
                deactivate_suredone_account(instance)
            elif instance.is_active and not user.is_active:
                activate_suredone_account(instance)


main_subscription_canceled = Signal(providing_args=["stripe_sub"])
main_subscription_updated = Signal(providing_args=["stripe_sub"])
