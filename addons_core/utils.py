import hashlib
from decimal import Decimal

import arrow
from django.db import transaction
from django.db.models import Q, Sum, Max
from django.utils import timezone
from django.utils.crypto import get_random_string
from django.utils.text import slugify

from leadgalaxy.models import GroupPlan
from lib.exceptions import capture_exception, capture_message
from shopified_core.utils import safe_int
from stripe_subscription.models import StripeCustomer
from stripe_subscription.stripe_api import stripe
from .models import INTERVAL_STRIPE_MAP, Addon, AddonBilling, AddonPrice, AddonUsage


class DictAsObject(dict):
    def __repr__(self):
        keys = list(self.keys())
        return self[keys[0]] if len(keys) else ''

    def __getattr__(self, k):
        if k[0] == "_":
            raise AttributeError(k)

        try:
            return self[k]
        except KeyError as err:
            raise AttributeError(*err.args)


def has_only_addons(stripe_subscription):
    for item in stripe_subscription['items']['data']:
        if item['price'] and item['price']['metadata'].get('type') != 'addon':
            return False

        if item['plan'] and item['plan']['metadata'].get('type') != 'addon':
            return False

    return True


def has_main_plan(customer_id):
    for subscription in get_customer_subscriptions(customer_id):
        if not has_only_addons(subscription):
            return True

    return False


def add_addon_plan(subscription):
    plan = GroupPlan.objects.filter(slug='addons-plan').first()
    if plan is None:
        return subscription

    item_data = {
        'price': plan.stripe_plan.stripe_id,
        'quantity': 1,
        'metadata': {'plan_id': plan.id}
    }

    first_item = subscription['items']['data'][0]['price']
    if first_item['recurring']['interval'] == 'month' \
            and first_item['recurring']['interval_count'] == 1:
        return stripe.Subscription.modify(subscription.id, items=[item_data])
    else:
        return stripe.Subscription.create(
            customer=subscription.customer,
            items=[item_data],
        )


def is_custom_subscription(subscription):
    return any([bool(i['plan']['metadata'].get('custom'))
               for i in subscription['items']['data']
               if i.get('plan')])


def get_customer_subscriptions(customer_id):
    subscription = {}
    subscriptions = {'has_more': True}
    while subscriptions['has_more']:
        subscriptions = stripe.Subscription.list(customer=customer_id, starting_after=subscription)
        for subscription in subscriptions:
            yield subscription


def merge_stripe_subscriptions(stripe_subscription):
    if not stripe_subscription['metadata'].get('netsuite_CF_funnel_id'):
        return stripe_subscription

    period_start = arrow.get(stripe_subscription.current_period_start).date()
    billing_data = stripe_subscription['items']['data'][0]['price']['recurring']
    click_funnels_id = stripe_subscription['metadata'].get('netsuite_CF_funnel_id')

    # Attach subscription to its equal in period and funnel id
    for new_subscription in get_customer_subscriptions(stripe_subscription.customer):
        if new_subscription.id == stripe_subscription.id:
            continue

        new_click_funnels_id = new_subscription['metadata'].get('netsuite_CF_funnel_id')
        if not new_click_funnels_id or new_click_funnels_id != click_funnels_id:
            continue

        new_period_start = arrow.get(new_subscription.current_period_start).date()
        if period_start != new_period_start:
            continue

        new_billing_data = new_subscription['items']['data'][0]['price']['recurring']
        if new_billing_data.interval_count != billing_data.interval_count \
                or new_billing_data.interval != billing_data.interval:
            continue

        try:
            for item in stripe_subscription['items']['data']:
                new_item = stripe.SubscriptionItem.create(
                    subscription=new_subscription.id,
                    price=item['price']['id'],
                    quantity=1,
                    proration_behavior='none',
                    metadata={'moved_from': stripe_subscription.id}
                )
                AddonUsage.objects.filter(
                    stripe_subscription_id=stripe_subscription.id,
                    stripe_subscription_item_id=item.id
                ).update(
                    stripe_subscription_id=new_subscription.id,
                    stripe_subscription_item_id=new_item.id
                )

            stripe.Subscription.delete(stripe_subscription.id)
            return new_subscription
        except:
            continue

        break

    return stripe_subscription


def get_item_from_subscription(subscription, item_id):
    for subscription_item in subscription['items']['data']:
        if subscription_item.id == item_id:
            return subscription_item

    raise Exception('Subscription Item not found')


def get_stripe_id(prefix=None):
    random_id = hashlib.md5(get_random_string(32).encode()).hexdigest()[:8]

    if prefix:
        random_id = f'{prefix}_{random_id}'

    return random_id


def sync_stripe_addon(*, addon=None, product=None):
    """Sync our Addons with stripe Products, provide only one kwarg and return
    its counterpart: addon -> product / product -> addon
    """
    if addon:
        data = {
            'name': f"{addon.title} Addon",
            'active': addon.is_active,
            'images': [addon.icon_url] if addon.icon_url else [],
            'type': 'service',
            'metadata': {'type': 'addon'},
        }
        if addon.description:
            data['description'] = addon.description

        if addon.stripe_product_id:
            del data['type']
            product = stripe.Product.modify(addon.stripe_product_id, **data)
        else:
            data['id'] = get_stripe_id('Addon')
            product = stripe.Product.create(**data)
            Addon.objects.filter(id=addon.id).update(stripe_product_id=product.id)

        return product

    elif product and product.metadata.get('type') == 'addon':
        data = {
            'title': product.name.replace(' Addon', ''),
            'description': product.description or '',
            'is_active': product.active,
            'stripe_product_id': product.id,
        }
        if product.images:
            data['icon_url'] = product.images[0]

        if product.metadata.get('slug'):
            data['slug'] = product.metadata.get('slug')

        addons = Addon.objects.filter(stripe_product_id=product.id)
        if len(addons) > 0:
            addons.update(**data)
            addon = addons[0]
        else:
            if not data.get('slug'):
                data['slug'] = slugify(data['title'])
            return Addon.objects.create(**data)

        # Update prices
        price = {}
        prices = {'has_more': True}
        while prices['has_more']:
            prices = stripe.Price.list(product=product.id, starting_after=price)
            for price in prices['data']:
                sync_stripe_billing(price=price)

        return addon


def sync_stripe_billing(*, addon_price=None, price=None):
    """Sync our Billing and Prices with stripe Prices, provide only one kwarg and return
    its counterpart, some fields in stripe Price translate to a Billing record
    """
    if addon_price:
        price_data = {
            'currency': 'usd',
            'product': addon_price.billing.addon.stripe_product_id,
            'active': addon_price.billing.is_active,
            'amount': safe_int(addon_price.price * 100),
            'interval': INTERVAL_STRIPE_MAP[addon_price.billing.interval],
            'interval_count': addon_price.billing.interval_count,
            'trial_period_days': addon_price.billing.trial_period_days,
            'metadata': {
                'iterations': addon_price.iterations,
                'sort_order': addon_price.sort_order,
                'type': 'addon',
                'group': '',
            }
        }

        if addon_price.stripe_price_id:
            existing_price = stripe.Price.retrieve(addon_price.stripe_price_id)

            # Price and interval fields can't be updated using API
            has_same_price = existing_price['unit_amount'] == price_data['amount']
            has_same_interval = (
                existing_price['recurring']['interval'] == price_data['interval']
                and existing_price['recurring']['interval_count'] == price_data['interval_count']
            )
            if has_same_price and has_same_interval:
                price = stripe.Plan.modify(addon_price.stripe_price_id, **{
                    'active': price_data['active'],
                    'metadata': price_data['metadata'],
                    'trial_period_days': price_data['trial_period_days']
                })

        if price is None:
            price_data['id'] = get_stripe_id('AddonPrice')
            price = stripe.Plan.create(**price_data)
            AddonPrice.objects.filter(id=addon_price.id).update(stripe_price_id=price.id)

        return price

    elif price and price.metadata.get('type') == 'addon':
        addon = Addon.objects.filter(stripe_product_id=price.product).first()
        if addon is None:
            return None

        addon_price = None
        billing = None

        addon_prices = AddonPrice.objects.select_related('billing').filter(
            stripe_price_id=price.id,
            billing__addon_id=addon.id
        )
        if len(addon_prices) > 0:
            addon_price = addon_prices[0]
            billing = addon_price.billing

        billing_data = {
            'is_active': price.active,
            'trial_period_days': price.recurring.trial_period_days or 0,
            'interval': INTERVAL_STRIPE_MAP[price.recurring.interval],
            'interval_count': price.recurring.interval_count,
        }

        if billing is not None:
            AddonBilling.objects.filter(id=billing.id).update(**billing_data)

        elif price.metadata.get('group'):
            # Billing must exist to bind a Stripe Price to a Dropified Addon
            billing = AddonBilling.objects.filter(group=price.metadata.group).first()
            if billing is None:
                billing_data['addon'] = addon
                billing_data['group'] = price.metadata.group
                billing = AddonBilling.objects.create(**billing_data)

        else:
            # Billing must exist to bind a Stripe Price to a Dropified Addon
            billing_data['addon'] = addon
            billing = AddonBilling.objects.create(**billing_data)

        price_data = {
            'billing_id': billing.id,
            'price': Decimal(price.unit_amount) / 100,
            'iterations': price.metadata.get('iterations', 0),
            'sort_order': price.metadata.get('sort_order', 0),
            'stripe_price_id': price.id,
        }

        if price.metadata.get('nickname'):
            price_data['price_descriptor'] = price.metadata.get('nickname')

        # AddonPrice signal may cause a loop on stripe price.updated event
        if addon_price is not None:
            AddonPrice.objects.filter(id=addon_price.id).update(**price_data)
        else:
            # Prevent loop in signal by not calling stripe if created obj has stripe_price_id
            addon_price = AddonPrice.objects.create(**price_data)

        return addon_price


def create_stripe_subscription(addon_usage):
    # Prevent duplicated subscriptions
    if addon_usage.stripe_subscription_item_id:
        return None

    # Prevent subscribing a day before trial ends
    if arrow.get(addon_usage.start_at).date() > arrow.get().date():
        return None

    if addon_usage.next_price is None:
        return None

    existing_subscriptions = stripe.Subscription.list(
        customer=addon_usage.user.stripe_customer.customer_id,
        price=addon_usage.next_price.stripe_price_id
    )['data']
    if len(existing_subscriptions) > 0:
        raise Exception(f'Duplicate subscription to Addon found in <AddonUsage: {addon_usage.id}>')

    subscription_item = None
    # Add addon in existing subscriptions with the same billing cycle
    customer_id = addon_usage.user.stripe_customer.customer_id
    for subscription in get_customer_subscriptions(customer_id):
        # Add item to a custom subscription breaks stripe webhooks matching
        # customer.subscription.(created|updated|deleted)
        if is_custom_subscription(subscription):
            continue

        period_start = arrow.get(subscription.current_period_start).date()
        if arrow.get(addon_usage.next_billing).date() != period_start:
            continue

        billing_data = subscription['items']['data'][0]['price']['recurring']
        has_same_interval = (INTERVAL_STRIPE_MAP[billing_data.interval] == addon_usage.billing.interval
                             and billing_data.interval_count == addon_usage.billing.interval_count)
        if not has_same_interval:
            continue

        try:
            subscription_item = stripe.SubscriptionItem.create(
                subscription=subscription.id,
                price=addon_usage.next_price.stripe_price_id,
                quantity=1,
                proration_behavior='always_invoice',
                proration_date=subscription.current_period_start,
                metadata={'addon_usage_id': addon_usage.id},
            )

            addon_usage.stripe_subscription_id = subscription.id
            addon_usage.stripe_subscription_item_id = subscription_item.id
        except:
            continue

        break

    if subscription_item is None:
        try:
            subscription = stripe.Subscription.create(
                customer=addon_usage.user.stripe_customer.customer_id,
                items=[{
                    'price': addon_usage.next_price.stripe_price_id,
                    'quantity': 1,
                    'metadata': {'addon_usage_id': addon_usage.id},
                }],
            )
        except:
            capture_exception()
            cancel_addon_usages([addon_usage])
            return None

        finally:
            subscription_item = subscription['items']['data'][0]

            addon_usage.stripe_subscription_id = subscription.id
            addon_usage.stripe_subscription_item_id = subscription_item.id

    addon_usage.next_billing = addon_usage.get_next_billing_date()
    addon_usage.save()

    return subscription_item


def update_stripe_subscription(addon_usage):
    if not addon_usage.stripe_subscription_item_id:
        return None

    subscription = stripe.Subscription.retrieve(addon_usage.stripe_subscription_id)
    subscription_item = get_item_from_subscription(subscription, addon_usage.stripe_subscription_item_id)

    # Prices can have limited iterations in a subscription, replace prices when due
    if subscription_item.price.id != addon_usage.next_price.stripe_price_id:
        remove_item_id = subscription_item.id
        item_count = len(subscription['items']['data'])

        if addon_usage.next_price is None:
            cancel_addon_usages([addon_usage])
        else:
            subscription_item = stripe.SubscriptionItem.create(
                subscription=subscription.id,
                price=addon_usage.next_price.stripe_price_id,
                quantity=1,
                proration_behavior='none',
                metadata={'addon_usage_id': addon_usage.id},
            )

            item_count += 1
            addon_usage.stripe_subscription_item_id = subscription_item.id
            addon_usage.next_billing = addon_usage.get_next_billing_date()
            addon_usage.save()

        # Stripe subscriptions must have at least one active plan/product
        if item_count == 1:
            stripe.Subscription.delete(subscription.id)
        else:
            stripe.SubscriptionItem.delete(remove_item_id)

    return subscription_item


def create_usage_from_stripe(subscription, subscription_item):
    if subscription.metadata.get('moved_to'):
        return None

    price = AddonPrice.objects.filter(stripe_price_id=subscription_item.price.id).first()
    if price is None:
        return None

    stripe_customer = StripeCustomer.objects.filter(customer_id=subscription.customer).first()
    if stripe_customer is None:
        return None

    addon_usage = AddonUsage.objects.update_or_create(
        user=stripe_customer.user,
        billing=price.billing,
        cancelled_at=None,
        defaults={
            'start_at': arrow.get(subscription.billing_cycle_anchor).date(),
            'next_billing': arrow.get(subscription.current_period_end).date(),
            'stripe_subscription_id': subscription.id,
            'stripe_subscription_item_id': subscription_item.id,
        }
    )[0]
    stripe_customer.user.profile.addons.add(price.billing.addon)

    return addon_usage


@transaction.atomic
def cancel_addon_usages(addon_usages):
    if len(addon_usages) == 0:
        return False

    user = addon_usages[0].user
    user_addon_ids = user.profile.addons.values_list('id', flat=True)
    remaining_addon_ids = user.addonusage_set.exclude(
        Q(id__in=[a.id for a in addon_usages]) | Q(cancelled_at__isnull=False)
    ).values_list('billing__addon_id', flat=True)
    # Some addons might be installed on other subscriptions
    removed_addon_ids = [addon_id for addon_id in user_addon_ids if addon_id not in remaining_addon_ids]

    cancelled_ids = []
    subscriptions = {}
    for addon_usage in addon_usages:
        if not addon_usage.stripe_subscription_item_id:
            cancelled_ids.append(addon_usage.id)
            continue

        # Single API calls can be expensive
        subscription_id = addon_usage.stripe_subscription_id
        if subscription_id not in subscriptions:
            subscriptions[subscription_id] = stripe.Subscription.retrieve(subscription_id)

        try:
            subscription = subscriptions.get(subscription_id)
            subscription_item = get_item_from_subscription(
                subscription, addon_usage.stripe_subscription_item_id)

            if len(subscription['items']['data']) == 1:
                stripe.Subscription.delete(subscription.id)
            else:
                stripe.SubscriptionItem.delete(subscription_item.id, proration_behavior='none')
                subscriptions[subscription_id]['items']['data'] = filter(
                    lambda item: item.id != subscription_item.id,
                    subscription['items']['data']
                )

            cancelled_ids.append(addon_usage.id)
        except:
            removed_addon_ids.remove(addon_usage.billing.addon_id)
            capture_exception()

    user.profile.addons.through.objects.filter(
        addon_id__in=removed_addon_ids,
        userprofile=user.profile,
    ).delete()

    AddonUsage.objects.filter(id__in=cancelled_ids).update(
        is_active=False,
        cancelled_at=timezone.now(),
        stripe_subscription_item_id=''
    )

    return True


def cancel_stripe_addons(subscription, item_ids=None):
    addon_usages = AddonUsage.objects.filter(
        stripe_subscription_id=subscription.id,
        cancelled_at__isnull=True,
    )

    if item_ids:
        addon_usages = addon_usages.filter(stripe_subscription_item_id__in=item_ids)

    for addon_usage in addon_usages:
        addon_usage.stripe_subscription_item_id = ''

    return cancel_addon_usages(addon_usages)


def has_shopify_limit_exceeded(user, addon_billing=None, charge=None):
    """Get first active subscription and check the capped limit against
    all subscribed addon prices for current period
    """
    if charge is None:
        # Shopify allows only one store per subscription
        store = user.profile.get_shopify_stores().first()
        charges = store.shopify.RecurringApplicationCharge.find()
        for charge in charges:
            if charge.status == 'active':
                break
        else:
            raise Exception('Subscription Not Found')

    # Some shopify subscriptions have a base amount
    total_cost = Decimal(charge.price)

    # Sum cancelled addons for this month as well
    one_month_ago = arrow.get().shift(months=-1).floor('day').datetime
    addon_usages = AddonUsage.objects.filter(
        Q(cancelled_at__isnull=True) | (
            Q(cancelled_at__isnull=False)
            & Q(cancelled_at__gte=one_month_ago)
        ),
        user=user
    ).annotate(max_price=Max('billing__prices__price'))

    if addon_billing is not None:
        addon_usages = addon_usages.exclude(billing_id=addon_billing.id)
        total_cost += addon_billing.max_cost

    total_cost += addon_usages.aggregate(c=Sum('max_price'))['c'] or Decimal('0.0')
    if Decimal(charge.capped_amount) < total_cost:
        # When all addons are paid, sum just recently subscribed addon
        if charge.balance_remaining == 0 and addon_billing is not None:
            total_cost = charge.capped_amount + addon_billing.max_cost

        # Shopify bugs the subscription if we update below capped_amount
        if total_cost < Decimal(charge.capped_amount):
            capture_message('Shopify capped amount is lesser than updated amount', extra={
                'total_cost': total_cost,
                'capped_amount': charge.capped_amount,
                'user_id': user.id,
                'addon_billing': addon_billing.id if addon_billing else '-'
            })
            return False

        charge.customize(capped_amount=total_cost)
        return charge.update_capped_amount_url

    return False
