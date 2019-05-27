from django.conf import settings
from django.http import JsonResponse, HttpResponseRedirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.urls import reverse
from django.views.decorators.csrf import csrf_protect

from raven.contrib.django.raven_compat.models import client as raven_client

from shopified_core import permissions
from shopified_core.utils import app_link
from leadgalaxy.models import GroupPlan, ShopifyStore, ClippingMagic, CaptchaCredit
from analytic_events.models import PlanSelectionEvent

from .models import ShopifySubscription


@csrf_protect
def subscription_plan(request):
    user = request.user

    if user.profile.get_shopify_stores().count() != 1:
        return JsonResponse({'error': 'Please make sure you\'ve added your store'}, status=422)

    try:
        plan_id = request.POST.get('plan', request.GET.get('plan'))
        plan = GroupPlan.objects.get(id=plan_id)
    except GroupPlan.DoesNotExist:
        return JsonResponse({'error': 'Selected plan not found'}, status=404)

    if not plan.is_shopify():
        return JsonResponse({'error': 'Plan is not valid'}, status=422)

    store = user.profile.get_shopify_stores().first()
    is_shopify_staff = store.get_info['plan_name'] == 'staff'
    extra_description = '' if not is_shopify_staff else '- Shopify Staff 50% Discount'

    if plan.is_free:
        for charge in store.shopify.RecurringApplicationCharge.find():
            if charge.status == 'active':
                charge.destroy()

        user.shopifysubscription_set.all().update(status='cancelled')
        user.profile.change_plan(plan)
    else:
        request.session['current_plan'] = user.profile.plan.id

        try:
            if plan.payment_interval != 'yearly':
                charge_type = 'recurring'
                price = plan.monthly_price
                if is_shopify_staff:
                    price = price / 2

                charge = store.shopify.RecurringApplicationCharge.create({
                    "test": settings.DEBUG,
                    "name": f'Dropified {plan.title} {extra_description}'.strip(),
                    "price": price,
                    "trial_days": plan.trial_days,
                    "return_url": app_link(reverse(subscription_activated))
                })
            else:
                charge_type = 'single'
                price = plan.monthly_price * 12
                if is_shopify_staff:
                    price = price / 2

                charge = store.shopify.ApplicationCharge.create({
                    "test": settings.DEBUG,
                    "name": f'Dropified {plan.title} {extra_description}'.strip(),
                    "price": price,
                    "trial_days": plan.trial_days,
                    "return_url": app_link(reverse(subscription_activated))
                })
        except Exception as e:
            if hasattr(e, 'response') and e.response.code == 401:
                return JsonResponse({
                    'status': 'redirect',
                    'location': app_link('/shopify/install', store.shop.split('.')[0], reinstall=store.id)
                })
            else:
                raven_client.captureException()
                return JsonResponse({'error': 'Shopify API Error'}, status=403)

        sub, created = ShopifySubscription.objects.update_or_create(
            subscription_id=charge.id,
            defaults={
                'user': user,
                'plan': plan,
                'store': store,
                'status': charge.status,
                'charge_type': charge_type
            }
        )

        sub.refresh(sub=charge)

        request.session['active_subscription'] = sub.id
        request.session['active_plan'] = plan.id
        request.session['charge_type'] = charge_type

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

        messages.success(request, 'Your plan has been successfully changed!')

        if request.session.get('charge_type') == 'single':
            store = request.user.profile.get_shopify_stores().first()
            if store:
                for charge in store.shopify.RecurringApplicationCharge.find():
                    if charge.status == 'active':
                        charge.destroy()

        request.user.shopifysubscription_set.exclude(id=charge_id).update(status='cancelled')

        request.user.set_config('_can_trial', False)

    else:
        request.user.profile.change_plan(GroupPlan.objects.get(id=request.session['current_plan']))

        messages.warning(request, 'Your plan was not changed because the charge was declined')

    return HttpResponseRedirect('/')


@login_required
def subscription_charged(request, store):
    charge_id = request.GET['charge_id']

    store = ShopifyStore.objects.get(id=store)
    permissions.user_can_view(request.user, store)

    charge = store.shopify.ApplicationCharge.find(charge_id)

    if charge.status == 'accepted':
        charge.activate()

        charge = request.session['shopiyf_charge']
        purchase_title = ''

        if charge['type'] == 'captcha':
            purchase_title = 'Captcha'

            try:
                captchacredit = CaptchaCredit.objects.get(user=request.user.models_user)
                captchacredit.remaining_credits += charge['credits']
                captchacredit.save()

            except CaptchaCredit.DoesNotExist:
                captchacredit.objects.create(
                    user=request.user.models_user,
                    remaining_credits=charge['credits']
                )
        elif charge['type'] == 'clippingmagic':
            purchase_title = 'Clipping Magic'

            try:
                clippingmagic = ClippingMagic.objects.get(user=request.user.models_user)
                clippingmagic.remaining_credits += charge['credits']
                clippingmagic.save()

            except ClippingMagic.DoesNotExist:
                ClippingMagic.objects.create(
                    user=request.user.models_user,
                    remaining_credits=charge['credits']
                )
        else:
            messages.warning(request, 'Unknown Charge Type')
            return HttpResponseRedirect('/')

        del request.session['shopiyf_charge']

        messages.success(request, 'You\'ve successfully purchased {} of {} credits!'.format(charge['credits'], purchase_title))

    else:
        messages.warning(request, 'Your purchase was not completed because the charge was declined')

    return HttpResponseRedirect('/')
