import json
from decimal import Decimal

import arrow
from django.db.models import F

import stripe
from lib.exceptions import capture_message
from stripe_subscription.models import CustomStripePlan, CustomStripeSubscription


def get_next_day(date: arrow.Arrow, day: int) -> arrow.Arrow:
    """Returns month ceiling or closest day after provided date
    """
    if day > date.ceil('month').day:
        return date.ceil('month')
    days_ahead = day - date.day
    if days_ahead < 0:  # Target day already happened this month
        days_ahead += date.ceil('month').day
    return date.shift(days=days_ahead)


def get_stripe_subscription(user):
    addons_subscription = user.customstripesubscription_set.filter(
        custom_plan__type='addons_subscription').first()

    if not addons_subscription:
        plan = CustomStripePlan.objects.get(type='addons_subscription')

        billing_day = arrow.get().day
        plan_subscription = user.stripesubscription_set.first()
        if plan_subscription and plan_subscription.period_start:
            billing_day = plan_subscription.period_start.day

        billing_cycle_ends = get_next_day(arrow.get(), billing_day)
        stripe_subscription = stripe.Subscription.create(
            customer=user.stripe_customer.customer_id,
            plan=plan.stripe_id,
            billing_cycle_anchor=billing_cycle_ends.ceil('day').timestamp,
            metadata={'custom_plan_id': plan.stripe_id, 'user_id': user.id,
                      'custom': True,
                      'custom_plan_type': 'addons_subscription'}
        )

        addons_subscription = CustomStripeSubscription.objects.create(
            data=json.dumps(stripe_subscription),
            status=stripe_subscription.status,
            period_start=arrow.get(stripe_subscription.current_period_start).datetime,
            period_end=arrow.get(stripe_subscription.current_period_end).datetime,
            user=user,
            custom_plan=plan,
            subscription_id=stripe_subscription.id,
            subscription_item_id=stripe_subscription['items']['data'][0]["id"],
        )

    return addons_subscription


def add_stripe_subscription_item(stripe_subscription, amount: Decimal,
                                 addon_usage, period=None):
    if amount < 0:
        return False

    try:
        invoice = stripe.Invoice.upcoming(
            subscription=stripe_subscription.subscription_id,
            customer=stripe_subscription.customer_id
        )
    except:
        capture_message(f"No upcomming invoice for subscription {stripe_subscription.subscription_id}")
        return False

    amount = int(amount * 100)
    end = arrow.get(period.get('end'))
    start = arrow.get(period.get('start'))
    item_period = f"{start.format('MMM DD, YYYY')}-{end.format('MMM DD, YYYY')}"

    for item in invoice['lines']['data']:
        if item['metadata'].get('addon_usage_id') == str(addon_usage.id) \
                and item['metadata'].get('type') == 'addon_usage':
            stripe.InvoiceItem.modify(
                item['id'],
                amount=amount,
                period=period,
                metadata={
                    'item_period': item_period
                },
            )
            break
    else:
        stripe.InvoiceItem.create(
            customer=stripe_subscription.customer_id,
            subscription=stripe_subscription.subscription_id,
            amount=amount,
            currency='usd',
            description=addon_usage.addon.title,
            period=period,
            metadata={
                "type": 'addon_usage',
                "addon_usage_id": addon_usage.id,
                "item_period": item_period,
            },
        )
    return True


def charge_stripe_first_time(addon_usage):
    # InvoiceItem without subscription_id to Invoice single item
    stripe_subscription = get_stripe_subscription(addon_usage.user)
    stripe_subscription.subscription_id = None

    start, end, latest_charge = addon_usage.get_latest_charge(save=False)
    start = start.floor('day')
    end = end.floor('day')

    added = add_stripe_subscription_item(
        stripe_subscription=stripe_subscription,
        amount=latest_charge,
        addon_usage=addon_usage,
        period={
            "end": end.timestamp,
            "start": start.timestamp,
        },
    )

    item_period = f"{start.format('MMM DD, YYYY')}-{end.format('MMM DD, YYYY')}"
    invoice = stripe.Invoice.create(
        customer=stripe_subscription.customer_id,
        description=addon_usage.addon.title,
        metadata={
            'source': 'Dropified Addons - First Charge',
            'addon_usage_id': addon_usage.id,
            'item_period': item_period,
        }
    )
    response = invoice.pay()
    return added and response['paid']


def cancel_stripe_subscription(user):
    stripe_subscription = get_stripe_subscription(user)

    cancelled_addons = user.addonusage_set.exclude(
        billed_to__gte=F('cancelled_at'),
        cancelled_at__isnull=True,
    )

    # Don't charge all upcomming items immediately when invoice.pay()
    if user.addonusage_set.filter(is_active=True).exists():
        stripe_subscription.subscription_id = None

    charged_addons = 0
    addon_usage_ids = []
    for addon_usage in cancelled_addons:
        start, end, latest_charge = addon_usage.get_latest_charge(save=False)
        if latest_charge < 0:
            continue

        added = add_stripe_subscription_item(
            stripe_subscription=stripe_subscription,
            amount=latest_charge,
            addon_usage=addon_usage,
            period={
                "end": end.floor('day').timestamp,
                "start": start.floor('day').timestamp,
            },
        )
        if added:
            charged_addons += 1
            addon_usage_ids.append(str(addon_usage.id))
            addon_usage.save()

    invoice = stripe.Invoice.create(
        customer=stripe_subscription.customer_id,
        subscription=stripe_subscription.subscription_id,
        description=f"Addon{'s' if charged_addons > 1 else ''} Cancellation",
        metadata={
            'source': 'Dropified Addons',
            'addon_usage_ids': ','.join(addon_usage_ids),
        }
    )
    response = invoice.pay()
    return response['paid']


def cancel_addon_subscription(user):
    if user.is_stripe_customer():
        return cancel_stripe_subscription(user)
