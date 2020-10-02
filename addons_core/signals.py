import arrow
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

from lib.exceptions import capture_exception
from leadgalaxy.signals import main_subscription_canceled
from stripe_subscription.models import StripeSubscription
from .models import AddonUsage
from .utils import get_stripe_subscription, charge_stripe_first_time, cancel_addon_subscription


@receiver(main_subscription_canceled, sender=StripeSubscription, dispatch_uid='cancel_addons_at_subscription_end')
def cancel_addons_at_subscription_end(sender, **kwargs):
    try:
        for addon_usage in sender.user.addonusage_set.filter(is_active=True):
            addon_usage.cancelled_at = timezone.now()
            addon_usage.is_active = False
            addon_usage.save()

            sender.user.profile.addons.remove(addon_usage.addon)

        cancel_addon_subscription(sender.user)
    except:
        capture_exception(level='warning')


@receiver(post_save, sender=AddonUsage)
def set_addon_billing(sender, instance, created, **kwargs):
    if created:
        stripe_subscription = None
        shopify_subscription = None

        period_start = arrow.get(instance.created_at).shift(days=instance.get_trial_days_left())
        interval_day = period_start.day

        last_usage = AddonUsage.objects.filter(
            user=instance.user,
            cancelled_at__isnull=True,
        ).exclude(id=instance.id).first()
        if last_usage:
            billing_day = last_usage.billing_day
        else:
            billing_day = interval_day

        try:
            # Charge addon subscription on same day as plan subscription
            if instance.user.is_stripe_customer():
                stripe_subscription = get_stripe_subscription(instance.user)
                billing_day = stripe_subscription.period_start.day

            elif instance.user.profile.from_shopify_app_store():
                shopify_subscription = instance.user.get_current_shopify_subscription()
                subscription = shopify_subscription.refresh()
                billing_day = arrow.get(subscription.billing_on).to('utc').day
        except:
            capture_exception(level='warning')

        instance.billing_day = billing_day
        instance.interval_day = interval_day
        AddonUsage.objects.filter(id=instance.id).update(
            interval_day=instance.interval_day,
            billing_day=instance.billing_day,
        )

        added = False
        if instance.created_at.date() == period_start.date():
            if stripe_subscription is not None:
                added = charge_stripe_first_time(instance)

        if added:
            AddonUsage.objects.filter(id=instance.id).update(billed_to=instance.billed_to)
