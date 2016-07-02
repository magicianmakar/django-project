from django.http import JsonResponse
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_protect

import arrow

from raven.contrib.django.raven_compat.models import client as raven_client

from leadgalaxy.models import GroupPlan

from .models import StripeSubscription
from .stripe_api import stripe
from .utils import (
    SubscriptionException,
    eligible_for_trial_coupon,
    subscription_end_trial,
    update_subscription
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

    still_in_trial = False

    subscription = user.stripesubscription_set.latest('created_at')
    if subscription:
        sub = subscription.refresh()

        if sub.status == 'trialing':
            trial_delta = arrow.get(sub.trial_end) - arrow.utcnow()
            still_in_trial = sub.trial_end and trial_delta.days > 0

    if not user.stripe_customer.can_trial and not still_in_trial:
        try:
            subscription_end_trial(user, raven_client, delete_on_error=True)

        except SubscriptionException as e:
            return JsonResponse({'error': e.message}, status=500)

        except:
            raven_client.captureException()
            return JsonResponse({'error': 'Server Error'}, status=500)

    if eligible_for_trial_coupon(cus):
        cus.coupon = settings.STRIP_TRIAL_DISCOUNT_COUPON
        user.stripe_customer.stripe_save(cus)

    return JsonResponse({'status': 'ok'})


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

    stripe_customer = user.stripe_customer
    stripe_customer.can_trial = False
    stripe_customer.save()

    return JsonResponse({'status': 'ok'})


@login_required
@csrf_protect
def subscription_plan(request):
    user = request.user
    user.profile.create_stripe_customer()

    # import pdb; pdb.set_trace()

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

            if not still_in_trial:
                sub.trial_end = 'now'

            sub.save()

            profile = user.profile
            profile.plan = plan
            profile.save()

            return JsonResponse({'status': 'ok'})
        else:
            return JsonResponse({
                'error': 'You are already subscribed to this plan'},
                status=500
            )
    else:
        sub = stripe.Subscription.create(
            customer=user.stripe_customer.customer_id,
            plan=plan.stripe_plan.stripe_id,
            metadata={'plan_id': plan.id, 'user_id': user.id}
        )

        update_subscription(user, plan, sub)

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

    return JsonResponse({'status': 'ok'})
