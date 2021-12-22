import requests

from django.conf import settings
from django.contrib import messages
from django.urls import reverse
from django.utils.crypto import get_random_string
from django.views.generic.base import RedirectView

from .models import AliexpressAccount
from .settings import API_KEY, API_SECRET
from shopified_core.utils import app_link, external_link


class AuthorizeView(RedirectView):
    def get_redirect_url(self, *args, **kwargs):
        redirect_url = app_link(reverse('aliexpress.token'))
        if settings.DEBUG:
            # Aliexpress doesn't redirect to local links for some reason
            redirect_url = redirect_url.replace('dev.', 'app.')

        return external_link(
            url='https://oauth.aliexpress.com/authorize',
            response_type='code',
            client_id=API_KEY,
            redirect_uri=redirect_url,
            state=get_random_string(32),
            view='web',
            sp='ae'
        )


class TokenView(RedirectView):
    def get_redirect_url(self, *args, **kwargs):
        res = requests.post('https://oauth.aliexpress.com/token', data={
            'code': self.request.GET['code'],
            'grant_type': 'authorization_code',
            'client_id': API_KEY,
            'client_secret': API_SECRET,
        })

        if res.ok:
            account, created = AliexpressAccount.objects.update_or_create(
                user=self.request.user.models_user,
                aliexpress_user_id=res.json().get('user_id'),
                aliexpress_username=res.json().get('user_nick'),
                defaults={
                    'access_token': res.json().get('access_token'),
                    'data': res.text
                }
            )

            op = 'created' if created else 'updated'
            messages.success(self.request, f"Your Aliexpress account ({account.aliexpress_username}) was successfully {op}")

            return '/settings#aliexpress'
