from math import ceil

from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_http_methods
from django.core.urlresolvers import reverse

import arrow

from raven.contrib.django.raven_compat.models import client as raven_client

from shopified_core.utils import app_link
from leadgalaxy.models import GroupPlan
from leadgalaxy.models import ClippingMagic, ClippingMagicPlan, CaptchaCredit, CaptchaCreditPlan

from analytic_events.models import PlanSelectionEvent, BillingInformationEntryEvent

from .models import StripeSubscription
from .stripe_api import stripe
from .utils import (
    SubscriptionException,
    subscription_end_trial,
    update_subscription,
    get_recent_invoice,
    get_stripe_invoice,
    refresh_invoice_cache,
)


@login_required
@csrf_protect
def customer_source(request):
    token = request.POST.get('stripeToken')
    user = request.user

    user.profile.create_stripe_customer()

    cus = user.stripe_customer.retrieve()
    cus.source = token

    try:
        cus = user.stripe_customer.stripe_save(cus)

        if not user.first_name and not user.last_name:
            fullname = cus.sources.data[0].name.split(' ')
            user.first_name, user.last_name = fullname[0], ' '.join(fullname[1:])
            user.save()

    except stripe.CardError as e:
        raven_client.captureException()

        return JsonResponse({
            'error': 'Credit Card Error: {}'.format(e.message)
        }, status=500)

    except:
        raven_client.captureException()

        return JsonResponse({
            'error': 'Credit Card Error, Please try again'
        }, status=500)

    source = user.stripe_customer.source
    BillingInformationEntryEvent.objects.create(user=request.user, source=str(source))

    return JsonResponse({'status': 'ok'})


@login_required
@csrf_protect
def customer_source_delete(request):
    user = request.user
    user.profile.create_stripe_customer()

    cus = user.stripe_customer.retrieve()

    if len(cus.sources.data):
        cus.sources.retrieve(cus.sources.data[0].id).delete()

        return JsonResponse({'status': 'ok'})
    else:
        return JsonResponse({'error': 'You don\'t have an attached Card'}, status=500)


@login_required
@csrf_protect
def subscription_trial(request):
    user = request.user

    user.profile.create_stripe_customer()

    if not user.stripe_customer.can_trial:
        return JsonResponse({'error': 'You can not start a trial'}, status=403)

    try:
        plan = GroupPlan.objects.get(id=request.POST.get('plan'))
    except GroupPlan.DoesNotExist:
        return JsonResponse({'error': 'Selected plan not found'}, status=404)

    if not plan.is_stripe():
        return JsonResponse({'error': 'Plan is not valid'}, status=403)

    user.profile.apply_subscription(plan)

    PlanSelectionEvent.objects.create(user=request.user)

    stripe_customer = user.stripe_customer
    stripe_customer.can_trial = False
    stripe_customer.save()

    return JsonResponse({'status': 'ok'})


@login_required
@csrf_protect
def subscription_plan(request):
    user = request.user
    user.profile.create_stripe_customer()

    try:
        plan = GroupPlan.objects.get(id=request.POST.get('plan'))
    except GroupPlan.DoesNotExist:
        return JsonResponse({'error': 'Selected plan not found'}, status=404)

    if not plan.is_stripe():
        return JsonResponse({'error': 'Plan is not valid'}, status=403)

    if user.stripesubscription_set.exists():
        subscription = user.stripesubscription_set.latest('created_at')
        sub = subscription.refresh()

        if sub.plan.id != plan.stripe_plan.stripe_id:
            if sub.status == 'trialing':
                trial_delta = arrow.get(sub.trial_end) - arrow.utcnow()
                still_in_trial = sub.trial_end and trial_delta.days > 0
            else:
                still_in_trial = False

            sub.plan = plan.stripe_plan.stripe_id

            if user.get_config('try_plan'):
                sub.trial_end = arrow.utcnow().replace(days=14).timestamp
                user.set_config('try_plan', False)
            else:
                if not still_in_trial:
                    sub.trial_end = 'now'
                else:
                    sub.trial_end = arrow.get(sub.trial_end).timestamp

            try:
                sub.save()

            except (SubscriptionException, stripe.CardError, stripe.InvalidRequestError) as e:
                raven_client.captureException(level='warning')
                msg = 'Subscription Error: {}'.format(e.message)
                if 'This customer has no attached payment source' in e.message:
                    msg = 'Please add your billing information first'

                return JsonResponse({'error': msg}, status=500)

            except:
                raven_client.captureException()
                return JsonResponse({'error': 'Server Error'}, status=500)

            profile = user.profile
            profile.plan = plan
            profile.save()

            PlanSelectionEvent.objects.create(user=request.user)

            return JsonResponse({'status': 'ok'})
        else:
            return JsonResponse({
                'error': 'You are already subscribed to this plan'},
                status=500
            )
    else:
        try:
            sub = stripe.Subscription.create(
                customer=user.stripe_customer.customer_id,
                plan=plan.stripe_plan.stripe_id,
                metadata={'plan_id': plan.id, 'user_id': user.id}
            )

            update_subscription(user, plan, sub)

        except (SubscriptionException, stripe.CardError, stripe.InvalidRequestError) as e:
            raven_client.captureException(level='warning')
            msg = 'Subscription Error: {}'.format(e.message)
            if 'This customer has no attached payment source' in e.message:
                msg = 'Please add your billing information first'

            return JsonResponse({'error': msg}, status=500)

        except:
            raven_client.captureException()
            return JsonResponse({'error': 'Server Error'}, status=500)

        if not user.stripe_customer.can_trial:
            try:
                subscription_end_trial(user, raven_client, delete_on_error=True)

            except SubscriptionException as e:
                StripeSubscription.objects.filter(subscription_id=sub.id).delete()

                return JsonResponse({'error': e.message}, status=500)

            except:
                raven_client.captureException()
                return JsonResponse({'error': 'Server Error'}, status=500)

        profile = user.profile
        profile.plan = plan
        profile.save()

        PlanSelectionEvent.objects.create(user=request.user)

    return JsonResponse({'status': 'ok'})


@login_required
@csrf_protect
def clippingmagic_subscription(request):
    user = request.user
    paid = False

    invoice = None

    clippingmagic_plan = ClippingMagicPlan.objects.get(id=request.POST.get('plan'))

    if request.user.profile.from_shopify_app_store():
        store = user.profile.get_shopify_stores().first()

        request.session['shopiyf_charge'] = {
            'type': 'clippingmagic',
            'credits': clippingmagic_plan.allowed_credits
        }

        charge = store.shopify.ApplicationCharge.create({
            "name": "Dropified Clipping Magic - {} Credits".format(clippingmagic_plan.allowed_credits),
            "price": clippingmagic_plan.amount,
            "return_url": app_link(reverse('shopify_subscription.views.subscription_charged', kwargs={'store': store.id})),
        })

        return JsonResponse({
            'status': 'ok',
            'location': charge.confirmation_url
        })

    try:

        stripe.InvoiceItem.create(
            customer=user.stripe_customer.customer_id,
            amount=clippingmagic_plan.amount * 100,
            currency='usd',
            description='Clipping Magic - {} Credits'.format(clippingmagic_plan.allowed_credits),
        )

        invoice = stripe.Invoice.create(
            customer=user.stripe_customer.customer_id,
            description='Clipping Magic Credits',
            metadata={
                'user': user.id,
                'clippingmagic_plan': clippingmagic_plan.id
            }
        )

        invoice.pay()

        paid = True

        try:
            clippingmagic = ClippingMagic.objects.get(user=user)
            clippingmagic.remaining_credits += clippingmagic_plan.allowed_credits
            clippingmagic.save()

        except ClippingMagic.DoesNotExist:
            ClippingMagic.objects.create(
                user=user,
                remaining_credits=clippingmagic_plan.allowed_credits
            )

    except ClippingMagicPlan.DoesNotExist:
        raven_client.captureException(level='warning')

        return JsonResponse({
            'error': 'Selected Credit not found'
        }, status=500)

    except stripe.CardError as e:
        raven_client.captureException(level='warning')

        return JsonResponse({
            'error': 'Credit Card Error: {}'.format(e.message)
        }, status=500)

    except stripe.InvalidRequestError as e:
        raven_client.captureException(level='warning')
        return JsonResponse({'error': 'Invoice payment error: {}'.format(e.message)}, status=500)

    except:
        raven_client.captureException(level='warning')

        return JsonResponse({
            'error': 'Credit Card Error, Please try again'
        }, status=500)

    finally:
        if not paid and invoice:
            invoice.closed = True
            invoice.save()

    return JsonResponse({'status': 'ok'})


@login_required
@csrf_protect
def captchacredit_subscription(request):
    user = request.user
    paid = False

    captchacredit_plan = CaptchaCreditPlan.objects.get(id=request.POST.get('plan'))

    if request.user.profile.from_shopify_app_store():
        store = user.profile.get_shopify_stores().first()

        request.session['shopiyf_charge'] = {
            'type': 'captcha',
            'credits': captchacredit_plan.allowed_credits
        }

        charge = store.shopify.ApplicationCharge.create({
            "name": "Dropified Auto Captcha - {} Credits".format(captchacredit_plan.allowed_credits),
            "price": captchacredit_plan.amount,
            "return_url": app_link(reverse('shopify_subscription.views.subscription_charged', kwargs={'store': store.id})),
        })

        return JsonResponse({
            'status': 'ok',
            'location': charge.confirmation_url
        })

    try:
        stripe.InvoiceItem.create(
            customer=user.stripe_customer.customer_id,
            amount=captchacredit_plan.amount * 100,
            currency='usd',
            description="Auto Captcha - {} Credits".format(captchacredit_plan.allowed_credits),
        )

        invoice = stripe.Invoice.create(
            customer=user.stripe_customer.customer_id,
            description='Auto Captcha Credits',
            metadata={
                'user': user.id,
                'captchacredit_plan': captchacredit_plan.id
            }
        )

        invoice.pay()

        paid = True

        try:
            captchacredit = CaptchaCredit.objects.get(user=user)
            captchacredit.remaining_credits += captchacredit_plan.allowed_credits
            captchacredit.save()

        except CaptchaCredit.DoesNotExist:
            captchacredit.objects.create(
                user=user,
                remaining_credits=captchacredit_plan.allowed_credits
            )

    except CaptchaCreditPlan.DoesNotExist:
        raven_client.captureException(level='warning')

        return JsonResponse({
            'error': 'Selected Credit not found'
        }, status=500)

    except stripe.CardError as e:
        raven_client.captureException(level='warning')

        return JsonResponse({
            'error': 'Credit Card Error: {}'.format(e.message)
        }, status=500)

    except stripe.InvalidRequestError as e:
        raven_client.captureException(level='warning')
        return JsonResponse({'error': 'Invoice payment error: {}'.format(e.message)}, status=500)

    except:
        raven_client.captureException(level='warning')

        return JsonResponse({
            'error': 'Credit Card Error, Please try again'
        }, status=500)

    finally:
        if not paid and invoice:
            invoice.closed = True
            invoice.save()

    return JsonResponse({'status': 'ok'})


@login_required
@csrf_protect
def subscription_cancel(request):
    user = request.user
    when = request.POST['when']

    subscription = user.stripesubscription_set.get(id=request.POST['subscription'])
    sub = subscription.refresh()

    if when == 'period_end':
        sub.delete(at_period_end=True)
        return JsonResponse({'status': 'ok'})

    elif when == 'immediately':
        if sub.status == 'active':
            invoice = get_recent_invoice(sub.customer, plan_invoices_only=True)

            if len(invoice.lines.data) == 1:
                period = invoice.lines.data[0].period
                invoiced_duration = period.end - period.start
                usage_duration = arrow.utcnow().timestamp - period.start

                if invoice.paid and invoice.closed and invoice.amount_due:
                    refound_amount = invoice.amount_due - ((usage_duration * invoice.amount_due) / invoiced_duration)
                    refound_amount = int(ceil(refound_amount / 100.0) * 100)

                    if 0 < refound_amount and refound_amount <= invoice.amount_due:
                        try:
                            stripe.Refund.create(
                                charge=invoice.charge,
                                amount=refound_amount
                            )
                        except:
                            raven_client.captureException()

                        raven_client.captureMessage('Subscription Refund', level='info', extra={
                            'amount': refound_amount,
                            'invoice': invoice.id,
                            'subscription': sub.id
                        })
                    else:
                        raven_client.captureMessage('Subscription Refund More Than Due', extra={
                            'amount': refound_amount,
                            'invoice': invoice.id,
                            'subscription': sub.id
                        })
            else:
                raven_client.captureMessage('Subscription Refund More Than One Invoice Item', extra={
                    'invoice': invoice.id,
                    'subscription': sub.id
                })

        sub.delete()
        return JsonResponse({'status': 'ok'})

    else:
        return JsonResponse({'error': 'Unknown "when" parameter'}, status=500)


@csrf_protect
@require_http_methods(['POST'])
@login_required
def invoice_pay(request, invoice_id):
    if not request.is_ajax():
        return JsonResponse({'error': 'Bad Request'}, status=500)

    response_404 = JsonResponse({'error': 'Page not found'}, status=404)
    if not request.user.is_recurring_customer():
        return response_404

    invoice = get_stripe_invoice(invoice_id)

    if not invoice:
        return response_404
    if not invoice.customer == request.user.stripe_customer.customer_id:
        return response_404

    if invoice.paid or invoice.closed:
        return JsonResponse({'error': 'Invoice is already paid or closed'}, status=500)
    else:
        try:
            invoice.pay()
            refresh_invoice_cache(request.user.stripe_customer)

        except stripe.error.CardError as e:
            raven_client.captureException(level='warning')
            return JsonResponse({'error': 'Invoice payment error: {}'.format(e.message)}, status=500)

        except stripe.InvalidRequestError as e:
            raven_client.captureException(level='warning')
            return JsonResponse({'error': 'Invoice payment error: {}'.format(e.message)}, status=500)

        except:
            raven_client.captureException()
            return JsonResponse({'error': 'Invoice was not paid, please try again.'}, status=500)

        else:
            return JsonResponse({'status': 'ok'}, status=200)
