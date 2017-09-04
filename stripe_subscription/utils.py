import datetime
import time

from decimal import Decimal, ROUND_HALF_UP

import simplejson as json

from django.conf import settings
from django.contrib.auth.models import User
from django.http import HttpResponse
from django.core.cache import cache
from django.db.models import Q

import arrow

from .models import StripeCustomer, StripeSubscription, StripeEvent, ExtraStore, ExtraCHQStore
from .stripe_api import stripe

from leadgalaxy.models import GroupPlan, UserProfile
from analytic_events.models import SuccessfulPaymentEvent


class SubscriptionException(Exception):
    pass


def update_subscription(user, plan, subscription):
    StripeSubscription.objects.update_or_create(
        subscription_id=subscription['id'],
        defaults={
            'user': user,
            'plan': plan,
            'data': json.dumps(subscription),
            'status': subscription['status'],
            'period_start': arrow.get(subscription['current_period_start']).datetime,
            'period_end': arrow.get(subscription['current_period_end']).datetime,

        }
    )


def update_customer(user, customer):
    StripeCustomer.objects.update_or_create(
        customer_id=customer['id'],
        defaults={
            'user': user,
            'data': json.dumps(customer)
        }
    )


def sync_subscription(user):
    if not user.is_recurring_customer():
        return False

    for sub in user.stripesubscription_set.all():
        try:
            sub.refresh()
        except stripe.InvalidRequestError:
            sub.delete()


def eligible_for_trial_coupon(cus):
    ''' Check if the passed Customer is eligible for trial coupon '''

    import arrow

    if len(cus['subscriptions']['data']):
        sub = cus['subscriptions']['data'][0]
        if sub['status'] == 'trialing':
            trial_delta = arrow.now() - arrow.get(sub['trial_start'])
            return trial_delta.days <= settings.STRIP_TRIAL_DISCOUNT_DAYS


def trial_coupon_offer_end(cus):
    import arrow

    if len(cus['subscriptions']['data']):
        sub = cus['subscriptions']['data'][0]
        if sub['status'] == 'trialing':
            return arrow.get(sub['trial_start']).replace(days=settings.STRIP_TRIAL_DISCOUNT_DAYS).humanize()


def format_coupon(cou, duration=True):
    text = ''

    if cou['percent_off']:
        text = '{}%'.format(cou['percent_off'])
    elif cou['amount_off']:
        text = '${:0.2f}'.format(cou['amount_off'] / 100.)

    if cou['duration'] == 'repeating':
        if cou['duration_in_months'] > 1:
            text = '{} Off Your First {} Months!'.format(text, cou['duration_in_months'])
        elif cou['duration_in_months'] == 1:
            text = '{} Off Your First Month!'.format(text)
    else:
        text = '{} Off!'.format(text)

    return text


def subscription_end_trial(user, raven_client, delete_on_error=False):
    for item in user.stripesubscription_set.all():
        sub = item.retrieve()

        if sub.trial_end:
            sub.trial_end = 'now'

            try:
                sub.save()
            except stripe.CardError as e:
                raven_client.captureException(level='warning')

                if delete_on_error:
                    sub.delete()

                raise SubscriptionException('Subscription Error: {}'.format(e.message))

            except stripe.InvalidRequestError as e:
                raven_client.captureException(level='warning')
                if delete_on_error:
                    sub.delete()

                message = e.message
                if 'This customer has no attached' in message:
                    message = 'You don\'t have any attached Credit Card'

                raise SubscriptionException('Subscription Error: {}'.format(message))

            except:
                raven_client.captureException()

                if delete_on_error:
                    sub.delete()

                raise SubscriptionException('Subscription Error, Please try again.')

            item.refresh()


def get_recent_invoice(customer_id):
    invoices = stripe.Invoice.list(limit=1, customer=customer_id).data
    return invoices[0] if len(invoices) else None


def resubscribe_customer(customer_id):
    # user = User.objects.get(stripe_customer__customer_id=customer_id)
    invoice = get_recent_invoice(customer_id)
    if not invoice:
        return False

    if invoice.closed and not invoice.paid and invoice.total:
        invoice.closed = False
        invoice.save()

        invoice.pay()

        return True

    return False


def have_extra_stores(user):
    stores_count = user.profile.get_shopify_stores().count() + user.profile.get_chq_stores().count()

    return user.profile.plan.stores != -1 and stores_count > user.profile.plan.stores


def extra_store_invoice(store, extra=None, chq=False):
    if extra is None:
        if chq:
            extra = ExtraCHQStore.objects.get(store=store)
        else:
            extra = ExtraStore.objects.get(store=store)

    invoice_item = stripe.InvoiceItem.create(
        customer=store.user.stripe_customer.customer_id,
        amount=2700,
        currency="usd",
        description=u"Additional Store: {}".format(store.title)
    )

    extra.status = 'active'
    extra.last_invoice = invoice_item.id

    if extra.period_start and extra.period_end:
        extra.period_start = extra.period_end
        extra.period_end = arrow.get(extra.period_end).replace(days=30).datetime
    else:
        extra.period_start = arrow.utcnow().datetime
        extra.period_end = arrow.utcnow().replace(days=30).datetime

    extra.save()

    invoice_item.description = u'{} ({} through {})'.format(
        invoice_item.description,
        arrow.get(extra.period_start).format('MM/DD'),
        arrow.get(extra.period_end).format('MM/DD'))

    invoice_item.save()


def invoice_extra_stores():
    """
    Find Extra Stores that need to be invoiced
    """
    invoiced = 0

    extra_stores = ExtraStore.objects.filter(status__in=['pending', 'active']) \
                                     .exclude(store__is_active=False) \
                                     .exclude(user__profile__plan__stores=-1) \
                                     .filter(Q(period_end__lte=arrow.utcnow().datetime) |
                                             Q(period_end=None))
    for extra in extra_stores:
        ignore = False
        if not extra.store.is_active or extra.user.profile.plan.is_free:
            extra.status = 'disabled'
            extra.save()
            ignore = True

        if extra.user.profile.get_shopify_stores().count() + extra.user.profile.get_chq_stores().count() <= 1:
            extra.user.extrastore_set.all().update(status='disabled')
            extra.user.extrachqstore_set.all().update(status='disabled')
            ignore = True

        if ignore:
            continue

        extra_store_invoice(extra.store, extra=extra)
        invoiced += 1

    extra_stores = ExtraCHQStore.objects.filter(status__in=['pending', 'active']) \
        .exclude(store__is_active=False) \
        .exclude(user__profile__plan__stores=-1) \
        .filter(Q(period_end__lte=arrow.utcnow().datetime) |
                Q(period_end=None))
    for extra in extra_stores:
        ignore = False
        if not extra.store.is_active or extra.user.profile.plan.is_free:
            extra.status = 'disabled'
            extra.save()
            ignore = True

        if extra.user.profile.get_shopify_stores().count() + extra.user.profile.get_chq_stores().count() <= 1:
            extra.user.extrastore_set.all().update(status='disabled')
            extra.user.extrachqstore_set.all().update(status='disabled')
            ignore = True

        if ignore:
            continue

        extra_store_invoice(extra.store, extra=extra, chq=True)
        invoiced += 1

    return invoiced


def process_webhook_event(request, event_id, raven_client):
    event = stripe.Event.retrieve(event_id)

    StripeEvent.objects.update_or_create(
        event_id=event.id,
        defaults={
            'event_type': event.type,
            'data': json.dumps(event),
        }
    )

    if event.type == 'invoice.payment_failed':
        invoice = event.data.object

        try:
            customer = StripeCustomer.objects.get(customer_id=invoice.customer)
        except StripeCustomer.DoesNotExist:
            raven_client.captureException(level='warning')
            return HttpResponse('Customer Not Found')

        if customer.have_source() and invoice.attempted:
            from shopified_core.utils import send_email_from_template

            user = User.objects.get(stripe_customer__customer_id=invoice.customer)
            send_email_from_template(
                tpl='invoice_payment_failed.html',
                subject='Your most recent invoice payment failed',
                recipient=user.email,
                data={
                    'username': user.get_first_name(),
                    'amount': '${:0.2f}'.format(invoice.total / 100.),
                    'event_id': event.id.split('_').pop(),
                    'invoice_id': invoice.id.split('_').pop(),
                },
                nl2br=False
            )

            return HttpResponse('Email Notification Sent')

        elif not customer.have_source():
            sub = customer.user.stripesubscription_set.first()
            if not sub:
                return HttpResponse('Subscription Not found')

            sub = sub.retrieve()
            sub.delete()

            return HttpResponse('Subscription Deleted')

        else:
            return HttpResponse('ok')

    # elif event.type == 'customer.source.created':
        # cus = stripe.Customer.retrieve(event.data.object.customer)
        # if cus.delinquent:
        #     resub = resubscribe_customer(cus.id)
        #     print 'ReSubscribe Customer: {}'.format(resub)
        #     return HttpResponse('ReSubscribe Customer: {}'.format(resub))

        # return HttpResponse('ok')

    elif event.type == 'customer.subscription.created':
        sub = event.data.object

        try:
            customer = StripeCustomer.objects.get(customer_id=sub.customer)
            customer.can_trial = False
            customer.save()

            reg_coupon = customer.user.get_config('registration_discount')
            if reg_coupon and not reg_coupon.startswith(':'):
                cus = stripe.Customer.retrieve(sub.customer)
                cus.coupon = reg_coupon
                cus.save()

                customer.user.set_config('registration_discount', u':{}'.format(reg_coupon))

        except StripeCustomer.DoesNotExist:
            raven_client.captureException(level='warning')
            return HttpResponse('Customer Not Found')

        try:
            stripe_sub = StripeSubscription.objects.get(subscription_id=sub.id)
            stripe_sub.refresh(sub=sub)
        except StripeSubscription.DoesNotExist:
            try:
                sub = stripe.Subscription.retrieve(sub.id)
                plan = GroupPlan.objects.get(Q(id=sub.metadata.get('plan_id')) |
                                             Q(stripe_plan__stripe_id=sub.plan.id))

                update_subscription(customer.user, plan, sub)
            except stripe.InvalidRequestError:
                pass

    elif event.type == 'customer.subscription.updated':
        sub = event.data.object

        try:
            stripe_sub = StripeSubscription.objects.get(subscription_id=sub.id)
            stripe_sub.refresh(sub=sub)
        except StripeSubscription.DoesNotExist:
            raven_client.captureException(level='warning')
            return HttpResponse('Subscription Not Found')

        trial_delta = arrow.get(sub.trial_end) - arrow.utcnow()
        if not sub.trial_end or trial_delta.days <= 0:
            customer = StripeCustomer.objects.get(customer_id=sub.customer)
            customer.can_trial = False
            customer.save()

        return HttpResponse('ok')

    elif event.type == 'customer.subscription.deleted':
        sub = event.data.object

        try:
            customer = StripeCustomer.objects.get(customer_id=sub.customer)
            customer.can_trial = False
            customer.save()

            profile = customer.user.profile

        except StripeCustomer.DoesNotExist:
            try:
                profile = UserProfile.objects.get(user=sub.metadata.user_id)
            except (UserProfile.DoesNotExist, AttributeError):
                raven_client.captureException(level='warning')
                return HttpResponse('Customer Not Found')

        current_plan = profile.plan
        if not profile.plan.is_free and profile.plan.is_stripe():
            profile.plan = GroupPlan.objects.get(default_plan=True)
            profile.save()
        elif not profile.plan.is_stripe():
            raven_client.captureMessage(
                'Plan was not changed to Free plan',
                extra={
                    'email': profile.user.email,
                    'plan': profile.plan.title,
                },
                level='warning')

        StripeSubscription.objects.filter(subscription_id=sub.id).delete()

        if current_plan == profile.plan:
            return HttpResponse('Subscription Deleted - Plan Unchanged')
        else:
            return HttpResponse('Subscription Deleted - Change plan From: {} To: {}'.format(
                current_plan.title, profile.plan.title))

    elif event.type == 'customer.updated':
        cus = event.data.object

        try:
            customer = StripeCustomer.objects.get(customer_id=cus.id)
            customer.refresh()
        except StripeCustomer.DoesNotExist:
            raven_client.captureException(level='warning')
            return HttpResponse('Customer Not Found')

        return HttpResponse('Customer Refreshed')

    elif event.type == 'customer.created':
        from leadgalaxy.tasks import invite_user_to_slack

        cus = event.data.object

        invite_user_to_slack.delay('users', {
            'email': cus.email,
            'firstname': '',
            'lastname': '',
        })

        return HttpResponse('Invited To Slack')

    elif event.type == 'customer.deleted':
        try:
            customer = StripeCustomer.objects.get(customer_id=event.data.object.id)
            customer.delete()
        except StripeCustomer.DoesNotExist:
            raven_client.captureException(level='warning')
            return HttpResponse('Customer Not Found')

        return HttpResponse('Customer Deleted')

    elif event.type in ['invoice.created', 'invoice.updated']:
        customer = event.data.object.customer
        try:
            stripe_customer = StripeCustomer.objects.get(customer_id=customer)
        except StripeCustomer.DoesNotExist:
            raven_client.captureException(level='warning')
            return HttpResponse('Customer Not Found')

        clear_invoice_cache(stripe_customer)

    elif event.type == 'charge.succeeded':
        charge = event.data.object

        try:
            user = User.objects.get(stripe_customer__customer_id=charge.customer)
        except User.DoesNotExist:
            return HttpResponse('User Not Found')

        SuccessfulPaymentEvent.objects.create(user=user, charge=str(charge))

        return HttpResponse('ok')

    else:
        return HttpResponse('Ignore Event')

    return HttpResponse('ok')


def get_stripe_invoice_list(stripe_customer):
    cache_key = 'invoices-' + stripe_customer.customer_id
    invoices = cache.get(cache_key)
    if invoices is None:
        invoices = [normalize_invoice(i) for i in stripe_customer.invoices]
        cache.set(cache_key, invoices, timeout=900)
    return invoices


def refresh_invoice_cache(stripe_customer):
    cache_key = 'invoices-' + stripe_customer.customer_id
    cache.delete(cache_key)
    invoices = [normalize_invoice(i) for i in stripe_customer.invoices]
    cache.set(cache_key, invoices, timeout=900)


def clear_invoice_cache(stripe_customer):
    cache_key = 'invoices-' + stripe_customer.customer_id
    cache.delete(cache_key)


def get_stripe_invoice(invoice_id, expand=None):
    expand = [] if expand is None else expand
    invoice = None

    while True:
        try:
            invoice = stripe.Invoice.retrieve(invoice_id, expand=expand)
        except stripe.error.RateLimitError:
            time.sleep(5)
            continue
        except stripe.error.InvalidRequestError:
            invoice = None
        break

    return normalize_invoice(invoice) if invoice else None


def normalize_invoice(invoice):
    invoice.date = datetime.datetime.fromtimestamp(float(invoice.date))
    invoice.period_start = datetime.datetime.fromtimestamp(float(invoice.period_start))
    invoice.period_end = datetime.datetime.fromtimestamp(float(invoice.period_end))
    invoice.total *= Decimal('0.01')
    invoice.subtotal *= Decimal('0.01')
    if invoice.tax:
        invoice.tax = invoice.tax * Decimal('0.01')
    if isinstance(invoice.charge, stripe.resource.Charge):
        invoice.charge = normalize_charge(invoice.charge)
    invoice.discount_amount = 0 * Decimal('0.01')
    if invoice.discount is not None:
        amount_off = invoice.discount['coupon'].get('amount_off')
        if amount_off is None:
            percent_off = invoice.discount['coupon']['percent_off'] * Decimal('0.01')
            invoice.discount_amount = (invoice.subtotal * percent_off).quantize(
                Decimal('0.01'), rounding=ROUND_HALF_UP)
        else:
            invoice.discount_amount = amount_off * Decimal('0.01')
    for line in invoice.lines.get('data', []):
        line['amount'] *= Decimal('0.01')
        if line.get('plan'):
            line['plan']['amount'] *= Decimal('0.01')
        if line.get('period'):
            if line['period'].get('start'):
                period_start = datetime.datetime.fromtimestamp(float(line['period']['start']))
                line['period']['start'] = period_start
            if line['period'].get('end'):
                period_end = datetime.datetime.fromtimestamp(float(line['period']['end']))
                line['period']['end'] = period_end

    return invoice


def normalize_charge(charge):
    charge.created = datetime.datetime.fromtimestamp(float(charge.created))
    charge.amount *= Decimal('0.01')
    if isinstance(charge.invoice, stripe.resource.Invoice):
        charge.invoice = normalize_invoice(charge.invoice)
    return charge
