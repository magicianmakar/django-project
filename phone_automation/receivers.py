from leadgalaxy.signals import main_subscription_canceled, main_subscription_updated
from lib.exceptions import capture_exception
from stripe_subscription.models import StripeSubscription
from shopify_subscription.models import ShopifySubscription
from django.db.models.signals import post_save
from django.dispatch import receiver


def process_callflex_recurings_delete(sender, **kwargs):
    try:
        if not sender:
            return

        main_stripe_subscription = sender
        custom_callflex_subscriptions = main_stripe_subscription.user.customstripesubscription_set.filter(
            custom_plan__type='callflex_subscription')
        for custom_callflex_subscription in custom_callflex_subscriptions:
            sub = custom_callflex_subscription.refresh()
            sub.delete(at_period_end=True)
    except:
        capture_exception(level='warning')


main_subscription_canceled.connect(process_callflex_recurings_delete)


def process_callflex_recurings_update(sender, **kwargs):
    try:
        if not sender:
            return

        main_stripe_subscription = sender
        sub = kwargs['stripe_sub']
        active_plans = []
        for item in sub['items']['data']:
            active_plans.append(item.id)

        custom_callflex_subscriptions = main_stripe_subscription.user.customstripesubscription_set.filter(
            custom_plan__type='callflex_subscription',
            subscription_id=main_stripe_subscription.subscription_id).exclude(subscription_item_id__in=active_plans)

        for custom_callflex_subscription in custom_callflex_subscriptions:
            custom_callflex_subscription.delete()
    except:
        capture_exception(level='warning')


main_subscription_updated.connect(process_callflex_recurings_update)


@receiver(post_save, sender=StripeSubscription)
def process_sub_upd_stripe(sender, instance, created, **kwargs):
    user = instance.user
    perm = user.can('phone_automation.use')
    try:
        if perm is False:
            # deleting phones
            for phone in user.twilio_phone_numbers.exclude(status='released'):
                phone.safe_delete()
            # deleting callflex subscriptions
            custom_callflex_subscriptions = user.customstripesubscription_set.filter(
                custom_plan__type='callflex_subscription')
            for custom_callflex_subscription in custom_callflex_subscriptions:
                custom_callflex_subscription.safe_delete()
    except:
        capture_exception(level='warning')


@receiver(post_save, sender=ShopifySubscription)
def process_sub_upd_shopify(sender, instance, created, **kwargs):
    user = instance.user
    perm = user.can('phone_automation.use')
    try:
        if perm is False:
            # deleting phones
            for phone in user.twilio_phone_numbers.exclude(status='released'):
                phone.delete()
    except:
        capture_exception(level='warning')
