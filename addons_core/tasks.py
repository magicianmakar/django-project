import arrow
from django.contrib.auth.models import User

from app.celery_base import celery_app, CaptureFailure
from lib.exceptions import capture_exception
from .models import Addon, AddonPrice, AddonUsage
from .utils import (
    sync_stripe_addon,
    sync_stripe_billing,
    create_stripe_subscription,
    create_shopify_charge,
    cancel_addon_usages,
)


@celery_app.task(base=CaptureFailure)
def create_or_update_addon_in_stripe(addon_id):
    addon = Addon.objects.get(id=addon_id)
    product = sync_stripe_addon(addon=addon)
    if product:
        return True


@celery_app.task(base=CaptureFailure)
def create_or_update_billing_in_stripe(addon_price_id):
    addon_price = AddonPrice.objects.get(id=addon_price_id)
    price = sync_stripe_billing(addon_price=addon_price)
    if price:
        return True


@celery_app.task(base=CaptureFailure)
def create_subscription_in_stripe(addon_usage_id):
    addon_usage = AddonUsage.objects.get(id=addon_usage_id)
    subscription_item = create_stripe_subscription(addon_usage)
    if not subscription_item and addon_usage.start_at == arrow.get().date():
        raise Exception(f'Subscription not created for <AddonUsage: {addon_usage.id}')


@celery_app.task(base=CaptureFailure)
def cancel_all_addons(user_id):
    user = User.objects.get(id=user_id)
    cancel_addon_usages(list(user.addonusage_set.filter(cancelled_at__isnull=True)))


@celery_app.task(base=CaptureFailure)
def create_charge_in_shopify(addon_usage_id):
    try:
        addon_usage = AddonUsage.objects.get(id=addon_usage_id)
        create_shopify_charge(addon_usage)
    except:
        capture_exception()
        cancel_addon_usages([addon_usage])
        addon_usage.delete()
