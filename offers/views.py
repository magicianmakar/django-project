import json
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.views import View
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect
from django.views.generic import TemplateView
from django.views.generic.detail import BaseDetailView

from stripe_subscription.stripe_api import stripe
from stripe_subscription.views import subscription_plan
from addons_core.api import AddonsApi
from .models import Offer, OfferCustomer


@method_decorator(login_required, name='dispatch')
class OfferDetailView(BaseDetailView, TemplateView):
    model = Offer
    template_name = 'offers/details.html'
    context_object_name = 'offer'

    @method_decorator(csrf_protect)  # Required to call AJAX subscribe
    def dispatch(self, request, *args, **kwargs):
        self.object = self.get_object()
        if self.object.slug != kwargs.get('slug'):
            return redirect('offers:details',
                            permanent=True,
                            pk=self.object.id,
                            slug=self.object.slug)

        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['seller'] = get_object_or_404(User, id=self.kwargs['seller_id'])
        if self.request.user.is_stripe_customer():
            discount = self.request.user.stripe_customer.get_data().get('discount') or {}
            context['current_coupon'] = discount.get('coupon')
        return context


@method_decorator(login_required, name='dispatch')
class SubscribeView(View):
    http_method_names = ['post']

    def post(self, request, pk, *args, **kwargs):
        if not request.user.is_stripe_customer():
            return JsonResponse({'error': "Upgrade not supported"}, status=403)

        offer = get_object_or_404(Offer, id=pk)
        stripe.Customer.modify(request.user.stripe_customer.customer_id, coupon=offer.coupon.stripe_coupon_id)
        amount = Decimal('0.0')
        if offer.plan:
            plan_response = subscription_plan(request)
            is_subscribed = 'already subscribed' in json.loads(plan_response.content).get('error', '')
            if not is_subscribed:
                amount += Decimal(offer.plan.get_total_cost())
                if plan_response.status_code != 200:
                    return plan_response

        addons_api = AddonsApi()
        for billing in offer.billings.all():
            addons_response = addons_api.post_install(
                request,
                request.user,
                {'billing': billing.id},
            )
            is_installed = 'already installed' in json.loads(addons_response.content).get('error', '')
            if not is_installed:
                amount += Decimal(billing.max_cost)
                if addons_response.status_code != 200:
                    return addons_response

        OfferCustomer.objects.get_or_create(
            offer=offer,
            customer=request.user,
            seller_id=self.kwargs('seller_id'),
            amount=amount
        )
        return JsonResponse({'status': 'ok'})
