import arrow
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views.generic.base import RedirectView

from alibaba_core.utils import TopAuthTokenCreateRequest

from .models import AlibabaAccount


@method_decorator(login_required, name='dispatch')
class AccessTokenRedirectView(RedirectView):
    permanent = True
    pattern_name = 'settings'

    def get_redirect_url(self, *args, **kwargs):
        auth_api = TopAuthTokenCreateRequest()
        token_data = auth_api.get_access_token(self.request.GET.get('code'))

        if token_data.get('error_msg'):
            error_question = ''
            if token_data.get('sub_code') == 'isv.param-authorization.code.invalid':
                error_question = 'Have you tried selecting an expiration date?'
            messages.error(self.request, f"{token_data.get('error_msg')} ({token_data.get('error_code')}). {error_question}")

            self.query_string = True  # Show alibaba code in params for CS
            return super().get_redirect_url(*args, **kwargs)

        user = self.request.user.models_user
        account, _ = AlibabaAccount.objects.update_or_create(user=user, defaults={
            'access_token': token_data['access_token'],
            'expired_at': arrow.get(token_data['expire_time'] / 1000).datetime,
            'alibaba_user_id': token_data['user_id'],
            'alibaba_email': token_data.get('email', ''),
        })
        account.allow_message_consumption()
        account.get_ecology_token(refresh=True)

        messages.success(self.request, "Your Dropified account is connected to Alibaba")
        return f"{super().get_redirect_url(*args, **kwargs)}#alibaba-settings"


@method_decorator(login_required, name='dispatch')
class ProductsRedirectView(RedirectView):
    permanent = False

    def get_redirect_url(self, *args, **kwargs):
        try:
            token = self.request.user.models_user.alibaba.first().get_ecology_token()
        except:
            messages.error(self.request, "Your Dropified account is not connected to Alibaba")
            return f"{reverse('settings')}#alibaba-settings"

        params = (
            ('wx_screen_direc', 'portrait'),
            ('wx_navbar_transparent', 'true'),
            ('path', '/p/dt0c706ur/index.html'),
            ('ecology_token', token),
        )
        return f"https://sale.alibaba.com/p/dt0c706ur/index.html?{urlencode(params)}"


@login_required
def products(request):

    return render(request, 'alibaba/products.html', {
        'alibaba': request.user.alibaba.first()
    })
