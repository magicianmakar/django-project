from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_http_methods
from django.urls import reverse

import arrow
import simplejson as json
from lib.exceptions import capture_exception

from shopified_core.utils import app_link
from leadgalaxy.models import GroupPlan
from leadgalaxy.models import ClippingMagic, ClippingMagicPlan, CaptchaCredit, CaptchaCreditPlan

from analytic_events.models import PlanSelectionEvent, BillingInformationEntryEvent

from addons_core.utils import cancel_addon_usages, move_addons_subscription
from .models import StripeSubscription
from .stripe_api import stripe
from .utils import (
    SubscriptionException,
    subscription_end_trial,
    update_subscription,
    get_stripe_invoice,
    refresh_invoice_cache,
    get_main_subscription_item,
    charge_single_charge_plan,
)
from phone_automation.models import CallflexCreditsPlan, CallflexCredit
from stripe_subscription.models import CustomStripePlan, CustomStripeSubscription


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

    except stripe.error.CardError as e:
        capture_exception()

        return JsonResponse({
            'error': 'Credit Card Error: {}'.format(str(e))
        }, status=500)

    except:
        capture_exception()

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

    if plan.single_charge:
        return charge_single_charge_plan(user, plan)

    if user.stripesubscription_set.exists():
        subscription = user.stripesubscription_set.latest('created_at')
        sub = subscription.refresh()
        sub_plan = subscription.get_main_subscription_item_plan(sub=sub)

        if sub_plan.id != plan.stripe_plan.stripe_id:
            if sub.status == 'past_due':
                return JsonResponse({'error': 'Currently your subscription is past due. '
                                              'Please check your payment methods to finalize pending invoices or contact '
                                              'Dropified support to get help.'}, status=403)
            if sub.status == 'trialing':
                trial_delta = arrow.get(sub.trial_end) - arrow.utcnow()
                still_in_trial = sub.trial_end and trial_delta.days > 0
            else:
                still_in_trial = False

            if user.get_config('try_plan'):
                sub.trial_end = arrow.utcnow().replace(days=14).timestamp
                user.set_config('try_plan', False)
            else:
                if not still_in_trial:
                    sub.trial_end = 'now'
                else:
                    sub.trial_end = arrow.get(sub.trial_end).timestamp

            if not user.get_config('research_upgraded') and "research" in user.profile.plan.slug:
                sub.trial_end = arrow.utcnow().replace(days=plan.trial_days).timestamp
                set_research_upgraded = True
            else:
                set_research_upgraded = False

            try:
                main_plan_item = get_main_subscription_item(sub)

                # check if new plan has different interval
                if main_plan_item['plan']['interval'] != plan.stripe_plan.interval and len(sub['items']['data']) > 1:
                    # move existing custom SI to new subscription
                    subscription.move_custom_subscriptions(sub)
                    move_addons_subscription(sub)

                stripe.SubscriptionItem.modify(
                    main_plan_item['id'],
                    plan=plan.stripe_plan.stripe_id
                )
                subscription.refresh()

                if set_research_upgraded:
                    user.set_config('research_upgraded', True)

                sub.save()

            except (SubscriptionException, stripe.error.CardError, stripe.error.InvalidRequestError) as e:
                capture_exception(level='warning')
                msg = 'Subscription Error: {}'.format(str(e))
                if 'This customer has no attached payment source' in str(e):
                    msg = 'Please add your billing information first'

                return JsonResponse({'error': msg}, status=500)

            except:
                capture_exception()
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

        except (SubscriptionException, stripe.error.CardError, stripe.error.InvalidRequestError) as e:
            capture_exception(level='warning')
            msg = 'Subscription Error: {}'.format(str(e))
            if 'This customer has no attached payment source' in str(e):
                msg = 'Please add your billing information first'

            return JsonResponse({'error': msg}, status=500)

        except:
            capture_exception()
            return JsonResponse({'error': 'Server Error'}, status=500)

        if not user.stripe_customer.can_trial:
            try:
                subscription_end_trial(user, delete_on_error=True)

            except SubscriptionException as e:
                StripeSubscription.objects.filter(subscription_id=sub.id).delete()

                return JsonResponse({'error': str(e)}, status=500)

            except:
                capture_exception()
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
        capture_exception(level='warning')

        return JsonResponse({
            'error': 'Selected Credit not found'
        }, status=500)

    except stripe.error.CardError as e:
        capture_exception(level='warning')

        return JsonResponse({
            'error': 'Credit Card Error: {}'.format(str(e))
        }, status=500)

    except stripe.error.InvalidRequestError as e:
        capture_exception(level='warning')
        return JsonResponse({'error': 'Invoice payment error: {}'.format(str(e))}, status=500)

    except:
        capture_exception(level='warning')

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
            CaptchaCredit.objects.create(
                user=user,
                remaining_credits=captchacredit_plan.allowed_credits
            )

    except CaptchaCreditPlan.DoesNotExist:
        capture_exception(level='warning')

        return JsonResponse({
            'error': 'Selected Credit not found'
        }, status=500)

    except stripe.error.CardError as e:
        capture_exception(level='warning')

        return JsonResponse({
            'error': 'Credit Card Error: {}'.format(str(e))
        }, status=500)

    except stripe.error.InvalidRequestError as e:
        capture_exception(level='warning')
        return JsonResponse({'error': 'Invoice payment error: {}'.format(str(e))}, status=500)

    except:
        capture_exception(level='warning')

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
        cancel_addon_usages(user.addonusage_set.filter(cancelled_at__isnull=True))
        return JsonResponse({'status': 'ok'})
    else:
        return JsonResponse({'error': 'Unknown "when" parameter'}, status=500)


@login_required
@csrf_protect
def subscription_activate(request):
    user = request.user

    subscription = user.stripesubscription_set.get(id=request.POST['subscription'])
    sub = subscription.refresh()

    sub.cancel_at_period_end = False
    sub.save()

    return JsonResponse({'status': 'ok'})


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
            capture_exception(level='warning')
            return JsonResponse({'error': 'Invoice payment error: {}'.format(str(e))}, status=500)

        except stripe.error.InvalidRequestError as e:
            capture_exception(level='warning')
            return JsonResponse({'error': 'Invoice payment error: {}'.format(str(e))}, status=500)

        except:
            capture_exception()
            return JsonResponse({'error': 'Invoice was not paid, please try again.'}, status=500)

        else:
            return JsonResponse({'status': 'ok'}, status=200)


@login_required
@csrf_protect
def callflexcredit_subscription(request):
    user = request.user
    paid = False

    callflexcredit_plan = CallflexCreditsPlan.objects.get(id=request.POST.get('plan'))

    if request.user.profile.from_shopify_app_store():
        store = user.profile.get_shopify_stores().first()

        request.session['shopiyf_charge'] = {
            'type': 'callflex_minutes',
            'credits': callflexcredit_plan.allowed_credits
        }

        charge = store.shopify.ApplicationCharge.create({
            "name": "CallFlex - {} Minutes".format(callflexcredit_plan.allowed_credits),
            "price": callflexcredit_plan.amount,
            "return_url": app_link(reverse('shopify_subscription.views.subscription_charged', kwargs={'store': store.id})),
        })

        return JsonResponse({
            'status': 'ok',
            'location': charge.confirmation_url
        })

    try:
        stripe.InvoiceItem.create(
            customer=user.stripe_customer.customer_id,
            amount=callflexcredit_plan.amount * 100,
            currency='usd',
            description="CallFlex - {} Minutes - Credits".format(callflexcredit_plan.allowed_credits),
        )

        invoice = stripe.Invoice.create(
            customer=user.stripe_customer.customer_id,
            description='CallFlex Minutes - Credits',
            metadata={
                'user': user.id,
                'captchacredit_plan': callflexcredit_plan.id
            }
        )

        invoice.pay()

        paid = True

        # adding minutes to DB

        callflexcredit = CallflexCredit()
        callflexcredit.user = user
        callflexcredit.stripe_invoice = invoice.id
        callflexcredit.purchased_credits = callflexcredit_plan.allowed_credits
        callflexcredit.save()

    except CallflexCreditsPlan.DoesNotExist:
        capture_exception(level='warning')

        return JsonResponse({
            'error': 'Selected Credit not found'
        }, status=500)

    except stripe.CardError as e:
        capture_exception(level='warning')

        return JsonResponse({
            'error': 'Credit Card Error: {}'.format(e.message)
        }, status=500)

    except stripe.InvalidRequestError as e:
        capture_exception(level='warning')
        return JsonResponse({'error': 'Invoice payment error: {}'.format(e.message)}, status=500)

    except:
        capture_exception(level='warning')

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
def callflex_subscription(request):
    user = request.user
    plan = CustomStripePlan.objects.get(id=request.POST.get('plan'))

    try:
        try:
            subscription = user.stripesubscription_set.latest('created_at')
            sub = subscription.refresh()
            sub_id_to_use = sub.id
        except StripeSubscription.DoesNotExist:
            sub = None

        user_callflex_subscription = user.customstripesubscription_set.filter(
            custom_plan__type='callflex_subscription').first()
        if user_callflex_subscription:
            sub_container = stripe.Subscription.retrieve(user_callflex_subscription.subscription_id)
        else:
            sub_container = sub
        if sub is None:
            need_new_sub_flag = True
        elif plan.interval != sub_container['items']['data'][0]["plan"]["interval"]:
            # check if main subscription match with interval and can be combined to
            if plan.interval != sub['items']['data'][0]["plan"]["interval"]:
                need_new_sub_flag = True
            else:
                # main sub can be used, take it instead
                sub_container = sub
                need_new_sub_flag = False
            # delete current subscription, as new one will be created with another interval
            if user_callflex_subscription:
                user_callflex_subscription.safe_delete()
        else:
            need_new_sub_flag = False

        # checking existing subscription
        user_callflex_subscription = user.customstripesubscription_set.filter(
            custom_plan__type='callflex_subscription').first()

        if user_callflex_subscription:
            stripe.SubscriptionItem.modify(
                user_callflex_subscription.subscription_item_id,

                plan=plan.stripe_id,
                metadata={'plan_id': plan.id, 'user_id': user.id}
            )
            si = stripe.SubscriptionItem.retrieve(user_callflex_subscription.subscription_item_id)
            custom_stripe_subscription = user_callflex_subscription
        else:
            if need_new_sub_flag:
                # creating new subscription for callflex plan
                sub_container = stripe.Subscription.create(
                    customer=user.stripe_customer.customer_id,
                    plan=plan.stripe_id,
                    metadata={'custom_plan_id': plan.id, 'user_id': user.id, 'custom': True,
                              'custom_plan_type': 'callflex_subscription'}
                )
                sub_id_to_use = sub_container.id
                si = stripe.SubscriptionItem.retrieve(sub_container['items']['data'][0]["id"])
            else:
                si = stripe.SubscriptionItem.create(
                    subscription=sub_id_to_use,
                    plan=plan.stripe_id,
                    metadata={'plan_id': plan.id, 'user_id': user.id}
                )

            custom_stripe_subscription = CustomStripeSubscription()

        custom_stripe_subscription.data = json.dumps(sub_container)
        custom_stripe_subscription.status = sub_container['status']
        custom_stripe_subscription.period_start = arrow.get(sub_container['current_period_start']).datetime
        custom_stripe_subscription.period_end = arrow.get(sub_container['current_period_end']).datetime
        custom_stripe_subscription.user = user
        custom_stripe_subscription.custom_plan = plan
        custom_stripe_subscription.subscription_id = sub_id_to_use
        custom_stripe_subscription.subscription_item_id = si.id

        custom_stripe_subscription.save()

    except CustomStripePlan.DoesNotExist:
        capture_exception(level='warning')

        return JsonResponse({
            'error': 'Selected Credit not found'
        }, status=500)

    except stripe.error.CardError as e:
        capture_exception(level='warning')

        return JsonResponse({
            'error': 'Credit Card Error: {}'.format(e.message)
        }, status=500)

    except stripe.error.InvalidRequestError:
        capture_exception(level='warning')
        return JsonResponse({'error': 'Invoice payment error. Please check your CC data. '}, status=500)
    except Exception as e:
        capture_exception(level='warning')

        return JsonResponse({
            'error': 'Error occurred {}'.format(e.message)
        }, status=500)

    return JsonResponse({'status': 'ok'})


@login_required
@csrf_protect
def custom_subscription_cancel(request):
    user = request.user

    try:
        custom_subscription = user.customstripesubscription_set.get(id=request.POST['subscription'])
        custom_subscription.safe_delete()

    except stripe.error.InvalidRequestError as e:
        capture_exception(level='warning')
        return JsonResponse({'error': 'Invoice payment error: {}'.format(e.message)}, status=500)

    return JsonResponse({'status': 'ok'})
