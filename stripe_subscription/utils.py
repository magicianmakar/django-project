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

from .models import (
    StripeCustomer,
    StripeSubscription,
    ExtraSubUser,
    ExtraStore, ExtraCHQStore,
    ExtraWooStore,
    ExtraGearStore,
    ExtraBigCommerceStore,
    CustomStripeSubscription
)
from .stripe_api import stripe

from lib.exceptions import capture_exception, capture_message
from shopified_core.utils import safe_str
from leadgalaxy.models import GroupPlan, UserProfile
from leadgalaxy.utils import register_new_user
from analytic_events.models import SuccessfulPaymentEvent
from tapfiliate.tasks import commission_from_stripe, successful_payment
from leadgalaxy import signals
from shopified_core.utils import safe_int, safe_float


class SubscriptionException(Exception):
    pass


def get_main_subscription_item(sub):
    for item in sub['items']['data']:
        try:
            custom_flag = item['plan']['metadata']['custom']
            if custom_flag:
                continue
        except:
            return item


def get_main_subscription_item_plan(sub=None):
    plan_item = get_main_subscription_item(sub)
    if plan_item:
        return plan_item['plan']


def update_subscription(user, plan, subscription):
    return StripeSubscription.objects.update_or_create(
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
    return StripeCustomer.objects.update_or_create(
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
        except stripe.error.InvalidRequestError:
            sub.delete()


def eligible_for_trial_coupon(cus):
    ''' Check if the passed Customer is eligible for trial coupon '''

    if len(cus['subscriptions']['data']):
        sub = cus['subscriptions']['data'][0]
        if sub['status'] == 'trialing':
            trial_delta = arrow.now() - arrow.get(sub['trial_start'])
            return trial_delta.days <= settings.STRIP_TRIAL_DISCOUNT_DAYS


def trial_coupon_offer_end(cus):
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


def subscription_end_trial(user, delete_on_error=False):
    for item in user.stripesubscription_set.all():
        sub = item.retrieve()

        if sub.trial_end:
            sub.trial_end = 'now'

            try:
                sub.save()
            except stripe.error.CardError as e:
                if delete_on_error:
                    sub.delete()

                raise SubscriptionException('Subscription Error: {}'.format(str(e)))

            except stripe.error.InvalidRequestError as e:
                if delete_on_error:
                    sub.delete()

                message = str(e)
                if 'This customer has no attached' in message:
                    message = 'You don\'t have any attached Credit Card'

                raise SubscriptionException('Subscription Error: {}'.format(message))

            except:
                capture_exception()

                if delete_on_error:
                    sub.delete()

                raise SubscriptionException('Subscription Error, Please try again.')

            item.refresh()


def get_recent_invoice(customer_id, plan_invoices_only=False):
    if not plan_invoices_only:
        invoices = stripe.Invoice.list(limit=1, customer=customer_id).data
        if len(invoices):
            return invoices[0]
    else:
        invoices = stripe.Invoice.list(limit=10, customer=customer_id).data
        for i in invoices:
            if not i.description or 'Credits' not in i.description:
                return i

    return None


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
    stores_count = user.profile.get_stores_count()

    return user.profile.plan.stores != -1 and stores_count > user.profile.plan.stores and not user.profile.plan.is_paused


def have_extra_subusers(user):
    subusers_count = user.profile.get_sub_users_count()

    return user.profile.plan.sub_users_limit != -1 and subusers_count > user.profile.plan.sub_users_limit and not user.profile.plan.is_paused


def have_wrong_extra_stores_count(extra):
    user = extra.user

    # Wrong extra stores found will be ignored
    cache_key = 'user_extra_stores_ignored_{}'.format(user.id)
    extra_stores_ignored = cache.get(cache_key, [])
    if extra_stores_ignored:
        if extra.id in extra_stores_ignored:
            return True

    extra_stores = get_active_extra_stores(ExtraStore.objects.filter(user=user), current_period=False)
    extra_chq_stores = get_active_extra_stores(ExtraCHQStore.objects.filter(user=user), current_period=False)
    extra_woo_stores = get_active_extra_stores(ExtraWooStore.objects.filter(user=user), current_period=False)
    extra_bigcommerce_stores = get_active_extra_stores(ExtraBigCommerceStore.objects.filter(user=user), current_period=False)
    extra_gear_stores = get_active_extra_stores(ExtraGearStore.objects.filter(user=user), current_period=False)
    current_extra_count = len(extra_stores)
    current_extra_count += len(extra_chq_stores)
    current_extra_count += len(extra_woo_stores)
    current_extra_count += len(extra_gear_stores)
    current_extra_count += len(extra_bigcommerce_stores)

    stores_count = user.profile.get_stores_count()
    stores_limit = user.profile.plan.stores
    correct_extra_count = stores_count - stores_limit

    # We have some extra stores already included in the plan
    if current_extra_count > correct_extra_count:
        current_limit_increase = current_extra_count - correct_extra_count

        # Delete current extra store
        if extra.id:
            count = extra.delete()
            if count[0] > 0:
                current_limit_increase -= 1

        for extra_store in extra_stores:
            # Remove extra store if limit is not reached
            if current_limit_increase > 0:
                current_limit_increase -= 1
                extra_stores_ignored.append(extra_store.id)
                extra_store.delete()

        for extra_store in extra_chq_stores:
            if current_limit_increase > 0:
                current_limit_increase -= 1
                extra_stores_ignored.append(extra_store.id)
                extra_store.delete()

        for extra_store in extra_woo_stores:
            if current_limit_increase > 0:
                current_limit_increase -= 1
                extra_stores_ignored.append(extra_store.id)
                extra_store.delete()

        for extra_store in extra_gear_stores:
            if current_limit_increase > 0:
                current_limit_increase -= 1
                extra_stores_ignored.append(extra_store.id)
                extra_store.delete()

        for extra_store in extra_bigcommerce_stores:
            if current_limit_increase > 0:
                current_limit_increase -= 1
                extra_stores_ignored.append(extra_store.id)
                extra_store.delete()

        cache.set(cache_key, extra_stores_ignored, timeout=900)
        return True

    return False


def have_wrong_extra_subusers_count(extra):
    user = extra.user

    # Wrong extra subusers found will be ignored
    cache_key = 'user_extra_subusers_ignored_{}'.format(user.id)
    extra_subusers_ignored = cache.get(cache_key, [])
    if extra_subusers_ignored:
        if extra.id in extra_subusers_ignored:
            return True

    extra_subusers = get_active_extra_subusers(ExtraSubUser.objects.filter(user=user), current_period=False)
    current_extra_count = len(extra_subusers)

    subusers_count = user.profile.get_sub_users_count()
    subusers_limit = user.profile.plan.sub_users_limit
    correct_extra_count = subusers_count - subusers_limit

    # We have some extra subusers already included in the plan
    if current_extra_count > correct_extra_count:
        current_limit_increase = current_extra_count - correct_extra_count

        # Delete current extra subuser
        if extra.id:
            count = extra.delete()
            if count[0] > 0:
                current_limit_increase -= 1

        for extra_subuser in extra_subusers:
            # Remove extra subuser if limit is not reached
            if current_limit_increase > 0:
                current_limit_increase -= 1
                extra_subusers_ignored.append(extra_subuser.id)
                extra_subuser.delete()

        cache.set(cache_key, extra_subusers_ignored, timeout=900)
        return True

    return False


def get_active_extra_stores(extra_queryset, current_period=True):
    active_extra = extra_queryset.filter(status__in=['pending', 'active']) \
                                 .exclude(store__is_active=False) \
                                 .exclude(user__profile__plan__stores=-1)

    if current_period:
        active_extra = active_extra.filter(
            Q(period_end__lte=arrow.utcnow().datetime) | Q(period_end=None))

    return active_extra


def get_active_extra_subusers(extra_queryset, current_period=True):
    active_extra = extra_queryset.filter(status__in=['pending', 'active']) \
                                 .exclude(store__is_active=False) \
                                 .exclude(user__profile__plan__sub_users_limit=-1)

    if current_period:
        active_extra = active_extra.filter(
            Q(period_end__lte=arrow.utcnow().datetime) | Q(period_end=None))

    return active_extra


def get_subscribed_extra_stores(extra_model):
    for extra in get_active_extra_stores(extra_model.objects.all()):
        ignore = False
        if not extra.store.is_active \
                or extra.user.profile.plan.is_free \
                or extra.user.profile.plan.is_paused:
            extra.status = 'disabled'
            extra.save()
            ignore = True

        if extra.user.profile.get_stores_count() <= 1:
            extra.user.extrastore_set.all().update(status='disabled')
            extra.user.extrachqstore_set.all().update(status='disabled')
            extra.user.extrawoostore_set.all().update(status='disabled')
            extra.user.extrabigcommercestore_set.all().update(status='disabled')
            extra.user.extragearstore_set.all().update(status='disabled')
            ignore = True

        if not have_extra_stores(extra.user):
            ignore = True

        if have_wrong_extra_stores_count(extra):
            ignore = True

        if ignore:
            continue

        yield extra


def get_subscribed_extra_subusers(extra_model):
    for extra in get_active_extra_subusers(extra_model.objects.all()):
        ignore = False
        if extra.user.profile.plan.is_free \
                or extra.user.profile.plan.is_paused:
            extra.status = 'disabled'
            extra.save()
            ignore = True

        if extra.user.profile.get_sub_users_count() <= 1:
            extra.user.extra_sub_user.all().update(status='disabled')
            ignore = True

        if not have_extra_subusers(extra.user):
            ignore = True

        if have_wrong_extra_subusers_count(extra):
            ignore = True

        if ignore:
            continue

        yield extra


def extra_store_invoice(store, extra=None):
    if extra is None:
        extra = store.extra.first()

    # calculate the cost of extra store from the field.
    extra_store_cost = store.user.profile.plan.extra_store_cost
    extra_store_cost = int(extra_store_cost * 100)  # convert to cents

    invoice_item = stripe.InvoiceItem.create(
        customer=store.user.stripe_customer.customer_id,
        amount=extra_store_cost,
        currency="usd",
        description="Additional {} Store: {}".format(extra._invoice_name, store.title)
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

    invoice_item.description = '{} ({} through {})'.format(
        invoice_item.description,
        arrow.get(extra.period_start).format('MM/DD'),
        arrow.get(extra.period_end).format('MM/DD'))

    invoice_item.save()


def extra_subuser_invoice(user, extra=None):
    if extra is None:
        extra = user.extra_sub_user.first()

    # calculate the cost of extra store from the field.
    extra_subuser_cost = user.profile.plan.extra_subuser_cost
    extra_subuser_cost = int(extra_subuser_cost * 100)  # convert to cents

    invoice_item = stripe.InvoiceItem.create(
        customer=user.stripe_customer.customer_id,
        amount=extra_subuser_cost,
        currency="usd",
        description="Additional {}: {}".format(extra._invoice_name, user.email)
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

    invoice_item.description = '{} ({} through {})'.format(
        invoice_item.description,
        arrow.get(extra.period_start).format('MM/DD'),
        arrow.get(extra.period_end).format('MM/DD'))

    invoice_item.save()


def invoice_extra_stores():
    """
    Find Extra Stores that need to be invoiced
    """
    invoiced = 0

    for extra in get_subscribed_extra_stores(ExtraStore):
        extra_store_invoice(extra.store, extra=extra)
        invoiced += 1

    for extra in get_subscribed_extra_stores(ExtraCHQStore):
        extra_store_invoice(extra.store, extra=extra)
        invoiced += 1

    for extra in get_subscribed_extra_stores(ExtraWooStore):
        extra_store_invoice(extra.store, extra=extra)
        invoiced += 1

    for extra in get_subscribed_extra_stores(ExtraGearStore):
        extra_store_invoice(extra.store, extra=extra)
        invoiced += 1

    for extra in get_subscribed_extra_stores(ExtraBigCommerceStore):
        extra_store_invoice(extra.store, extra=extra)
        invoiced += 1

    return invoiced


def invoice_extra_subusers():
    """
    Find Extra Subusers that need to be invoiced
    """
    invoiced = 0

    for extra in get_subscribed_extra_subusers(ExtraSubUser):
        extra_subuser_invoice(extra.user, extra=extra)
        invoiced += 1

    return invoiced


def process_webhook_event(request, event_id):
    event = stripe.Event.retrieve(event_id)

    if event.type == 'invoice.payment_failed':
        invoice = event.data.object

        try:
            customer = StripeCustomer.objects.get(customer_id=invoice.customer)
        except StripeCustomer.DoesNotExist:
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
                }
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

    elif event.type == 'invoice.payment_succeeded':
        invoice = event.data.object

        try:
            customer = StripeCustomer.objects.get(customer_id=invoice.customer)
            for item in invoice['lines']['data']:
                try:
                    # Stripe Plan metadata format:
                    # {"after_days":"89","switch_to_plan":"SA_07de7485", "trial_days_add":"275"}
                    if item['type'] == 'subscription' and item['plan']['metadata'].get('plan_autoswitch'):
                        plan_autoswitch_json = json.loads(item['plan']['metadata']['plan_autoswitch'])
                        stripe_sub = StripeSubscription.objects.get(subscription_id=item['id'])
                        days_passed = (arrow.now().timestamp - int(stripe_sub.created_at.timestamp())) // 86400

                        if days_passed > int(plan_autoswitch_json['after_days']):
                            # switching to plan
                            plan = GroupPlan.objects.get(stripe_plan__stripe_id=plan_autoswitch_json['switch_to_plan'])
                            if plan.is_stripe():
                                # adding trial (from metadata)
                                trial_end = arrow.now().timestamp + 86400 * int(plan_autoswitch_json['trial_days_add'])
                                stripe.Subscription.modify(
                                    stripe_sub.subscription_id,
                                    trial_end=trial_end,
                                    proration_behavior='none'
                                )
                                # updating subscription item (switching plan)
                                stripe.SubscriptionItem.modify(
                                    item['subscription_item'],
                                    plan=plan.stripe_plan.stripe_id,
                                    metadata={'plan_id': plan.id, 'user_id': customer.user.id},
                                    proration_behavior='none'
                                )

                                customer.user.profile.change_plan(plan)
                                sub = stripe_sub.refresh()

                                update_subscription(customer.user, plan, sub)
                except:
                    capture_exception(level='warning')

        except StripeCustomer.DoesNotExist:
            return HttpResponse('Customer not found (1st invoice, skipping)')

        return HttpResponse('ok')
    elif event.type == 'customer.subscription.created':
        sub = event.data.object
        sub_plan = get_main_subscription_item_plan(sub)

        # check for all custom subscriptions in lines data
        for item in sub['items']['data']:
            try:
                if item['plan']['metadata']['custom']:
                    stripe_sub = CustomStripeSubscription.objects.get(subscription_id=sub.id)
                    stripe_sub.refresh(sub=sub)
            except:
                pass

        # checking if it's a custom single subscription ( when mixing yearly/monthly )
        try:
            if sub['plan']['metadata']['custom']:
                capture_message('Single Custom Subscription Event', level='info')
                return HttpResponse('Subscription Updated')
        except:
            pass

        created = False

        try:
            customer = StripeCustomer.objects.get(customer_id=sub.customer)
            customer.can_trial = False
            customer.save()

            reg_coupon = customer.user.get_config('registration_discount')
            try:
                if reg_coupon and not reg_coupon.startswith(':'):
                    cus = stripe.Customer.retrieve(sub.customer)
                    cus.coupon = reg_coupon
                    cus.save()

                customer.user.set_config('registration_discount', ':{}'.format(reg_coupon))
            except:
                capture_exception(level='warning')

        except StripeCustomer.DoesNotExist:
            if sub_plan.metadata.get('click_funnels') or sub_plan.metadata.get('lifetime') or request.GET.get('cf'):
                stripe_customer = stripe.Customer.retrieve(sub.customer)

                fullname = ''
                email = stripe_customer.email
                intercom_attrs = {
                    "register_source": 'clickfunnels',
                    "register_medium": 'webhook',
                }

                if stripe_customer.metadata and 'phone' in stripe_customer.metadata:
                    intercom_attrs['phone'] = stripe_customer.metadata.phone

                if stripe_customer.sources and stripe_customer.sources.data:
                    fullname = stripe_customer.sources.data[0].name

                user, created = register_new_user(email, fullname, intercom_attributes=intercom_attrs, without_signals=True)

                if created:
                    customer = update_customer(user, stripe_customer)[0]

                    if sub_plan.metadata.get('lifetime'):
                        user.set_config('_stripe_lifetime', sub_plan.id)
                else:
                    if user.have_stripe_billing():
                        customer = user.stripe_customer

                        customer.customer_id = sub.customer
                        customer.save()
                        customer.refresh()

                        StripeSubscription.objects.filter(user=user).delete()

                    else:
                        try:
                            customer = StripeCustomer.objects.create(
                                customer_id=sub.customer,
                                user=user
                            )

                            customer.refresh()
                        except:
                            capture_exception()
                            return HttpResponse('Cloud Not Register User')
            else:
                return HttpResponse('Customer Not Found')

        try:
            stripe_sub = StripeSubscription.objects.get(subscription_id=sub.id)
            stripe_sub.refresh(sub=sub)
        except StripeSubscription.DoesNotExist:
            try:
                sub = stripe.Subscription.retrieve(sub.id)
                plan = GroupPlan.objects.get(Q(id=sub.metadata.get('plan_id'))
                                             | Q(stripe_plan__stripe_id=sub_plan.id))

                if plan.is_stripe():
                    customer.user.profile.change_plan(plan)

                update_subscription(customer.user, plan, sub)

            except stripe.error.InvalidRequestError:
                pass

        if created:
            return HttpResponse('New User Registered')
        else:
            return HttpResponse('Subscription Updated')

    elif event.type == 'customer.subscription.updated':
        sub = event.data.object

        # check for all custom subscriptions in lines data
        for item in sub['items']['data']:
            try:
                if item['plan']['metadata']['custom']:
                    stripe_sub = CustomStripeSubscription.objects.get(subscription_id=sub.id)
                    stripe_sub.refresh(sub=sub)
            except:
                pass

        # checking if it's a custom single subscription ( when mixing yearly/monthly )
        try:
            if sub['plan']['metadata']['custom']:
                capture_message('Single Custom Subscription Event', level='info')
                return HttpResponse('ok')
        except:
            pass

        try:
            stripe_sub = StripeSubscription.objects.get(subscription_id=sub.id)
            stripe_sub.refresh(sub=sub)

            # Firing custom signal about updating main user subscription
            signals.main_subscription_updated.send(sender=stripe_sub, stripe_sub=sub)

        except StripeSubscription.DoesNotExist:
            return HttpResponse('Subscription Not Found')

        trial_delta = arrow.get(sub.trial_end) - arrow.utcnow()
        if not sub.trial_end or trial_delta.days <= 0:
            StripeCustomer.objects.filter(customer_id=sub.customer).update(can_trial=False)

        return HttpResponse('ok')

    elif event.type == 'customer.subscription.deleted':
        sub = event.data.object

        # check for all custom subscriptions in lines data
        for item in sub['items']['data']:
            try:
                if item['plan']['metadata']['custom']:
                    stripe_sub = CustomStripeSubscription.objects.get(subscription_id=sub.id)
                    stripe_sub.delete()
            except:
                pass

        # checking if it's a custom single subscription ( when mixing yearly/monthly )
        try:
            if sub['plan']['metadata']['custom']:
                capture_message('Single Custom Subscription Event', level='info')
                return HttpResponse('Custom Subscription Deleted')
        except:
            pass

        try:
            customer = StripeCustomer.objects.get(customer_id=sub.customer)
            customer.can_trial = False
            customer.save()

            profile = customer.user.profile

        except StripeCustomer.DoesNotExist:
            try:
                profile = UserProfile.objects.get(user=sub.metadata.user_id)
            except (UserProfile.DoesNotExist, AttributeError):
                return HttpResponse('Customer Not Found')

        current_plan = profile.plan
        if not profile.plan.is_free and profile.plan.is_stripe() and not profile.plan_expire_at:
            profile.plan = GroupPlan.objects.get(default_plan=True)
            profile.save()

        stripe_sub = StripeSubscription.objects.filter(subscription_id=sub.id).first()
        StripeSubscription.objects.filter(subscription_id=sub.id).delete()

        # Firing custom signal about canceling main user subscription
        signals.main_subscription_canceled.send(sender=stripe_sub, stripe_sub=sub)

        if not profile.plan_expire_at:
            return HttpResponse('Subscription Deleted - Plan Exipre Set')
        elif current_plan == profile.plan:
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
            return HttpResponse('Customer Not Found')

        return HttpResponse('Customer Refreshed')

    elif event.type == 'customer.created':
        cus = event.data.object
        cache.set('affilaite_{}'.format(cus.id), True, timeout=604800)

        return HttpResponse('Invited To Slack')

    elif event.type == 'customer.deleted':
        try:
            customer = StripeCustomer.objects.get(customer_id=event.data.object.id)
            customer.delete()
        except StripeCustomer.DoesNotExist:
            return HttpResponse('Customer Not Found')

        return HttpResponse('Customer Deleted')

    elif event.type in ['invoice.created', 'invoice.updated']:
        customer = event.data.object.customer
        clear_invoice_cache(customer)

    elif event.type == 'charge.succeeded':

        charge = event.data.object

        if not charge.customer:
            return HttpResponse('Customer Is Not Set')

        try:
            user = User.objects.get(stripe_customer__customer_id=charge.customer)
            response_message = "User Found"
        except User.DoesNotExist:
            description = safe_str(charge.description)

            is_unlimited = request.POST.get('unlimited') or \
                ('Unlimited' in description and ('ECOM Jam' in description or '$997' in description)) or \
                (charge.metadata.get('products') in ['$997 Lifetime Offer', 'Dropified Lifetime Unlimited'])

            if is_unlimited:
                stripe_customer = stripe.Customer.retrieve(charge.customer)

                fullname = ''
                email = stripe_customer.email
                intercom_attrs = {
                    "register_source": 'clickfunnels',
                    "register_medium": 'webhook',
                }

                if stripe_customer.metadata and 'phone' in stripe_customer.metadata:
                    intercom_attrs['phone'] = stripe_customer.metadata.phone

                if stripe_customer.sources and stripe_customer.sources.data:
                    fullname = stripe_customer.sources.data[0].name

                user, created = register_new_user(email, fullname, intercom_attributes=intercom_attrs, without_signals=True)

                if not created:
                    StripeCustomer.objects.filter(user=user).delete()

                customer = update_customer(user, stripe_customer)[0]

                profile = user.profile
                if profile.subuser_parent:
                    profile.subuser_parent = None
                    profile.subuser_stores.clear()
                    profile.subuser_chq_stores.clear()
                    profile.save()

                plan = GroupPlan.objects.get(id=request.POST.get('plan', 31))
                profile.change_plan(plan)

                if plan.is_stripe():
                    profile.apply_subscription(plan)

                user.set_config('_stripe_lifetime', plan.id)

                SuccessfulPaymentEvent.objects.create(user=user, charge=json.dumps({
                    'charge': charge.to_dict(),
                    'count': 1
                }))

                return HttpResponse('New Registration to {}'.format(plan.title))

            response_message = 'User Not Found'

        commission_from_stripe.apply_async(
            args=[charge.id],
            countdown=600)  # Give time for the user to register/login to Dropified before handling this event (wait for conversion)

        successful_payment.apply_async(
            args=[charge.id],
            countdown=600)  # Give time for the user to register/login to Dropified before handling this event (wait for conversion)

        return HttpResponse(response_message)

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


def clear_invoice_cache(stripe_customer_id):
    cache_key = 'invoices-' + stripe_customer_id
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
    if isinstance(invoice.charge, stripe.Charge):
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
    if isinstance(charge.invoice, stripe.Invoice):
        charge.invoice = normalize_invoice(charge.invoice)
    return charge


def add_invoice(sub_container, invoice_type, amount, replace_flag=False, description="Custom Invoice Item"):

    amount = safe_float(amount)
    try:
        upcoming_invoice = stripe.Invoice.upcoming(subscription=sub_container.id)
    except:
        capture_message("No Upcoming Invoice. Skipping this user.")
        return False

    upcoming_invoice_item = False

    for item in upcoming_invoice['lines']['data']:
        try:
            if item['metadata']['type'] == invoice_type:
                upcoming_invoice_item = item
        except:
            pass

    if upcoming_invoice_item:
        if replace_flag:
            new_amount = amount * 100
        else:
            new_amount = safe_float(upcoming_invoice_item['metadata']['exact_amount']) + (amount * 100)

        stripe.InvoiceItem.modify(
            upcoming_invoice_item['id'],
            amount=safe_int(new_amount),
            metadata={"type": invoice_type, "exact_amount": new_amount}
        )
    else:
        upcoming_invoice_item = stripe.InvoiceItem.create(
            customer=sub_container.customer,
            subscription=sub_container.id,
            amount=safe_int(amount * 100),
            currency='usd',
            description=description,
            metadata={"type": invoice_type, "exact_amount": (amount * 100)}
        )

    return upcoming_invoice_item
