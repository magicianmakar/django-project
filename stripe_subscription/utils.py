import simplejson as json

from django.conf import settings
from django.contrib.auth.models import User
from django.http import HttpResponse

import arrow

from .models import StripeCustomer, StripeSubscription, StripeEvent, ExtraStore
from .stripe_api import stripe

from leadgalaxy.models import GroupPlan


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
    if not user.is_stripe_customer():
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
    return user.profile.get_active_stores().count() > user.profile.plan.stores


def extra_store_invoice(store, extra=None):
    if extra is None:
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


def invoice_extra_stores():
    """
    Find Extra Stores that need to be invoiced
    """

    from django.db.models import Q

    extra_stores = ExtraStore.objects.filter(store__is_active=True) \
                                     .filter(status__in=['pending', 'active']) \
                                     .filter(Q(period_end__lte=arrow.utcnow().datetime) |
                                             Q(period_end=None))

    invoiced = 0
    for extra in extra_stores:
        extra_store_invoice(extra.store, extra=extra)
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
        customer = StripeCustomer.objects.get(customer_id=invoice.customer)

        if customer.have_source() and invoice.attempted:
            from leadgalaxy.utils import send_email_from_template

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

        customer = StripeCustomer.objects.get(customer_id=sub.customer)
        customer.can_trial = False
        customer.save()

        try:
            stripe_sub = StripeSubscription.objects.get(subscription_id=sub.id)
            stripe_sub.refresh(sub=sub)
        except StripeSubscription.DoesNotExist:
            try:
                sub = stripe.Subscription.retrieve(sub.id)
                plan = GroupPlan.objects.get(id=sub.metadata.plan_id)

                update_subscription(customer.user, plan, sub)
            except stripe.InvalidRequestError:
                pass

    elif event.type == 'customer.subscription.updated':
        sub = event.data.object

        try:
            stripe_sub = StripeSubscription.objects.get(subscription_id=sub.id)
            stripe_sub.refresh(sub=sub)
        except StripeSubscription.DoesNotExist:
            pass

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
        except StripeCustomer.DoesNotExist:
            raven_client.captureException(level='warning')
            return HttpResponse('Customer Not Found')

        profile = customer.user.profile
        current_plan = profile.plan
        if not profile.plan.is_free and profile.plan.is_stripe():
            profile.plan = GroupPlan.objects.get(default_plan=True)
            profile.save()
        elif not profile.plan.is_stripe():
            raven_client.captureMessage(
                'Plan was not changed to Free plan',
                extra={
                    'email': customer.user.email,
                    'plan': profile.plan.title,
                },
                level='warning')

        StripeSubscription.objects.filter(subscription_id=sub.id).delete()

        customer = StripeCustomer.objects.get(customer_id=sub.customer)
        customer.can_trial = False
        customer.save()

        if current_plan == profile.plan:
            return HttpResponse('Subscription Deleted - Plan Unchanged')
        else:
            return HttpResponse('Subscription Deleted - Change plan From: {} To: {}'.format(
                current_plan.title, profile.plan.title))

    elif event.type == 'customer.updated':
        cus = event.data.object
        customer = StripeCustomer.objects.get(customer_id=cus.id)
        customer.refresh()

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

    elif event.type == 'invoice.updated':
        pass
    elif event.type == 'customer.subscription.trial_will_end':
        try:
            customer = StripeCustomer.objects.get(customer_id=event.data.object.customer)
        except StripeCustomer.DoesNotExist:
            raven_client.captureException(level='warning')
            return HttpResponse('Customer Not Found')

        if event.data.object.status == 'trialing' and not customer.have_source():
            trial_delta = arrow.get(event.data.object.trial_end) - arrow.utcnow()
            if trial_delta.days >= 2:  # Make sure it's not an activation event
                from leadgalaxy.utils import send_email_from_template

                send_email_from_template(
                    tpl='trial_ending_soon.html',
                    subject='Re: Trial Ends In 3 Days',
                    recipient=customer.user.email,
                    data={
                        'username': customer.user.get_first_name(),
                    },
                    nl2br=False
                )

                return HttpResponse('Trial Ending Email Sent')

        return HttpResponse('No Email Sent - Status: {} Have Source: {}'.format(
            event.data.object.status, customer.have_source()))

    elif event.type == 'invoice.payment_succeeded':
        pass
    else:
        return HttpResponse('Ignore Event')

    return HttpResponse('ok')
