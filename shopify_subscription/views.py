from django.http import JsonResponse, HttpResponseRedirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.urlresolvers import reverse
from django.views.decorators.csrf import csrf_protect

from shopified_core import permissions
from shopified_core.utils import app_link
from leadgalaxy.models import GroupPlan
# from leadgalaxy.models import ClippingMagic, ClippingMagicPlan, CaptchaCredit, CaptchaCreditPlan
from leadgalaxy.utils import get_plan

from analytic_events.models import PlanSelectionEvent

from .models import ShopifySubscription


@csrf_protect
def subscription_plan(request):
    user = request.user

    if user.profile.get_shopify_stores().count() != 1:
        return JsonResponse({'error': 'Please make sure you\'ve added your store'}, status=403)

    try:
        plan = GroupPlan.objects.get(id=request.POST.get('plan'))
    except GroupPlan.DoesNotExist:
        return JsonResponse({'error': 'Selected plan not found'}, status=404)

    if not plan.is_shopify():
        return JsonResponse({'error': 'Plan is not valid'}, status=403)

    store = user.profile.get_shopify_stores().first()

    if plan.is_free:
        for charge in store.shopify.RecurringApplicationCharge.find():
            if charge.status == 'active':
                charge.destroy()

        user.shopifysubscription_set.all().update(status='cancelled')
        user.profile.change_plan(plan)
    else:
        charge = store.shopify.RecurringApplicationCharge.create({
            "name": 'Dropified {}'.format(plan.title),
            "price": plan.monthly_price,
            "capped_amount": 100,
            "terms": "Dropified Monthly Subscription",
            "return_url": app_link(reverse('shopify_subscription.views.subscription_activated'))
        })

        sub, created = ShopifySubscription.objects.update_or_create(
            subscription_id=charge.id,
            defaults={
                'user': user,
                'plan': plan,
                'store': store,
                'status': charge.status,
            }
        )

        sub.refresh(sub=charge)

        user.shopifysubscription_set.exclude(id=sub.id).update(status='cancelled')

        request.session['active_subscription'] = sub.id
        request.session['active_plan'] = plan.id

    PlanSelectionEvent.objects.create(user=request.user)

    return JsonResponse({
        'status': 'ok',
        'location': charge.confirmation_url if not plan.is_free else '#'
    })


@login_required
def subscription_activated(request):
    charge_id = request.GET['charge_id']
    sub = ShopifySubscription.objects.get(subscription_id=charge_id)

    permissions.user_can_view(request.user, sub)
    charge = sub.refresh()

    if charge.status == 'accepted':
        charge.activate()

        if request.session.get('active_plan'):
            request.user.profile.change_plan(GroupPlan.objects.get(
                id=request.session.get('active_plan')))

            del request.session['active_plan']
    else:
        request.user.profile.change_plan(get_plan(
            payment_gateway='shopify',
            plan_slug='starter-shopify'))

    messages.success(request, 'Your plan has been successfully changed!')

    return HttpResponseRedirect('/')
