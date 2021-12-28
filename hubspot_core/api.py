import requests

from django.core.cache import cache
from django.conf import settings
from django.views.generic import View

from shopified_core.mixins import ApiResponseMixin
from shopified_core.utils import hash_text


class HubSpotApi(ApiResponseMixin, View):

    def post_verify(self, request, user, data):
        cache_key = f'hs_verify_token_{hash_text(user.email)}'
        hs_token = cache.get(cache_key)
        if not hs_token:
            r = requests.post(
                url='https://api.hubspot.com/conversations/v3/visitor-identification/tokens/create',
                json={
                    "email": user.email,
                    "firstName": user.first_name,
                    "lastName": user.last_name
                },
                params={'hapikey': settings.HUPSPOT_API_KEY}
            )

            r.raise_for_status()
            hs_token = r.json()['token']
            cache.set(cache_key, hs_token, timeout=3600)

        return self.api_success({
            'email': user.email,
            'token': hs_token
        })
