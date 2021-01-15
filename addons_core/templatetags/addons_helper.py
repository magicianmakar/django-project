from django import template
from django.db.models import Prefetch, Sum, F, DurationField
from django.db.models.functions import Coalesce, Now
from django.urls import reverse

from addons_core.models import Addon, AddonBilling, AddonUsage

register = template.Library()


@register.filter(takes_context=True)
def for_user(addon_billings, user):
    try:
        addon_billings = list(addon_billings)
    except:
        addon_billings = [addon_billings]

    if not user.is_authenticated:
        for addon_billing in addon_billings:
            addon_billing.user_price = addon_billing.prices.first()
            addon_billing.trial_days_left = addon_billing.trial_period_days
        return addon_billings

    subscriptions = AddonUsage.objects.filter(
        price_after_cancel__isnull=False,
        user=user
    ).select_related('price_after_cancel')
    cancel_subscriptions = AddonUsage.objects.filter(
        user=user,
        is_active=True,
        cancelled_at__isnull=False
    )
    addon_billings = AddonBilling.objects.filter(
        id__in=[b.id for b in addon_billings]
    ).prefetch_related(
        'prices',
        Prefetch('subscriptions', queryset=subscriptions),
        Prefetch('subscriptions', queryset=cancel_subscriptions, to_attr='cancel_subscriptions'),
    ).annotate(
        total_usage=Sum(
            Coalesce(F('subscriptions__cancelled_at'), Now()) - F('subscriptions__created_at'),
            output_field=DurationField()
        ),
    ).filter(is_active=True)

    for addon_billing in addon_billings:
        if not addon_billing:
            continue

        subscription = addon_billing.subscriptions.first()
        if subscription is None:
            addon_billing.user_price = addon_billing.prices.first()
        else:
            addon_billing.user_price = subscription.price_after_cancel

        if addon_billing.total_usage is None:
            addon_billing.trial_days_left = addon_billing.trial_period_days
        else:
            trial_days_left = addon_billing.trial_period_days - addon_billing.total_usage.days
            addon_billing.trial_days_left = trial_days_left if trial_days_left > 0 else 0

        addon_billing.cancel_at_period_end = False
        if len(addon_billing.cancel_subscriptions) > 0:
            addon_billing.cancel_at_period_end = addon_billing.cancel_subscriptions[0]

    return addon_billings


@register.filter(takes_context=True)
def addon_permalink(addon_id):
    try:
        return Addon.objects.get(id=addon_id).permalink
    except:
        return f"{reverse('user_profile')}#plan"
