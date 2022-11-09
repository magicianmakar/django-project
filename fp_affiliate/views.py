import requests

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views.generic import TemplateView

from . import settings as app_settings
from .utils import create_fp_user


class RedirectException(Exception):
    def __init__(self, url):
        self.url = url


class IndexView(TemplateView):
    template_name = 'fp_affiliate/index.html'

    def get(self, request, *args, **kwargs):
        try:
            return super().get(request, *args, **kwargs)
        except RedirectException as e:
            return HttpResponseRedirect(e.url)

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs: dict) -> dict:
        ctx = super().get_context_data(**kwargs)
        ctx['breadcrumbs'] = [{'title': 'Affiliate', 'url': reverse('fp_affiliate_index')}]

        # Search First Promoter for this customer
        r = requests.get(
            'https://firstpromoter.com/api/v1/promoters/show',
            params={
                'promoter_email': self.request.user.email,
            }, headers={
                'x-api-key': app_settings.FIRST_PROMOTER_API_KEY,
            }
        )

        affiliate = None

        if r.ok and 'promoter not found' not in r.text.lower():
            affiliate = r.json()

        promotion = None
        if affiliate:
            for p in affiliate['promotions']:
                if not p['hidden'] and not promotion:
                    promotion = p
                    break

        if promotion:
            promotion['sales_total'] = f'$ {promotion["sales_total"] / 100:,.2f}'

        ctx.update({
            'affiliate': affiliate,
            'promotion': promotion,
        })

        if affiliate:
            ctx['breadcrumbs'].append(f"{affiliate['email']}")

        if not affiliate and 'join' in self.request.GET:
            if create_fp_user(self.request.user):
                raise RedirectException(url=reverse('fp_affiliate_index'))
            else:
                messages.error(self.request, 'Could not add user to First Promoter')

        return ctx
