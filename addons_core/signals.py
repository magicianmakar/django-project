import arrow
from django.db.models.signals import post_save
from django.dispatch import receiver

from leadgalaxy.signals import main_subscription_canceled
from stripe_subscription.models import StripeSubscription
from .models import AddonUsage, Addon, AddonPrice
from .tasks import (
    create_or_update_addon_in_stripe,
    create_or_update_billing_in_stripe,
    create_subscription_in_stripe,
    create_charge_in_shopify,
)
from .utils import cancel_addon_usages


@receiver(main_subscription_canceled, sender=StripeSubscription, dispatch_uid='cancel_addons_at_subscription_end')
def cancel_addons_at_subscription_end(sender, **kwargs):
    cancel_addon_usages(sender.user.addonusage_set.filter(cancelled_at__isnull=True))


@receiver(post_save, sender=Addon)
def sync_addon_in_stripe(sender, instance, created, **kwargs):
    # No need to sync, only stripe webhook will "create" obj with "stripe_product_id"
    if not created or not instance.stripe_product_id:
        create_or_update_addon_in_stripe.apply_async(args=[instance.id], countdown=5)


@receiver(post_save, sender=AddonPrice)
def sync_billing_in_stripe(sender, instance, created, **kwargs):
    # No need to sync, only stripe webhook will "create" obj with "stripe_price_id"
    if not created or not instance.stripe_price_id:
        create_or_update_billing_in_stripe.apply_async(args=[instance.id], countdown=5)


@receiver(post_save, sender=AddonUsage)
def set_addon_subscription(sender, instance, created, **kwargs):
    if created and not instance.stripe_subscription_item_id:
        instance.start_at = instance.get_start_date()
        instance.next_billing = instance.start_at
        AddonUsage.objects.filter(id=instance.id).update(
            start_at=instance.start_at, next_billing=instance.next_billing)

        if instance.start_at != arrow.get().date():
            return True

        if instance.user.profile.from_shopify_app_store():
            create_charge_in_shopify.apply_async(args=[instance.id], countdown=5)

        elif instance.user.is_stripe_customer():
            create_subscription_in_stripe.apply_async(args=[instance.id], countdown=5)
