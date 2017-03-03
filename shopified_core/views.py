import traceback

from django.conf import settings
from django.contrib.auth import login as user_login
from django.contrib.auth import logout as user_logout
from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from django.views.generic import View

import requests
from raven.contrib.django.raven_compat.models import client as raven_client

from leadgalaxy.api import ShopifyStoreApi
from commercehq_core.api import CHQStoreApi

from .mixins import ApiResponseMixin
from .exceptions import ApiLoginException

import utils as core_utils


class ShopifiedApi(ApiResponseMixin, View):
    supported_stores = [
        'all',      # Common endpoint
        'shopify',  # Shopify Stores
        'chq'       # CommerceHQ Stores
    ]

    default = {
        'store_type': 'shopify',
        'version': 1
    }

    def dispatch(self, request, *args, **kwargs):
        for k, v in self.default.items():
            if not kwargs.get(k):
                kwargs[k] = v

        try:
            if kwargs['store_type'] not in self.supported_stores:
                return self.http_method_not_allowed(request, *args, **kwargs)

            method_names = [
                self.method_name(request.method, kwargs['store_type'], kwargs['target']),
                self.method_name(request.method, kwargs['target'])
            ]

            for method_name in method_names:
                handler = getattr(self, method_name, None)

                if handler:
                    return handler(request, **kwargs)

            if kwargs['store_type'] == 'shopify':
                return ShopifyStoreApi.as_view()(request, *args, **kwargs)
            elif kwargs['store_type'] == 'chq':
                return CHQStoreApi.as_view()(request, *args, **kwargs)
            else:
                raise Exception("Unknown Store Type")

        except PermissionDenied as e:
            raven_client.captureException()
            reason = e.message if e.message else "You don't have permission to perform this action"

            return self.api_error('Permission Denied: %s' % reason, status=403)

        except requests.Timeout:
            raven_client.captureException()
            return self.api_error('API Request Timeout', status=501)

        except ApiLoginException as e:
            return self.api_error(e.description(), status=401)

        except:
            if settings.DEBUG:
                traceback.print_exc()

            raven_client.captureException()

            return self.api_error('Internal Server Error')

    def post_login(self, request, **kwargs):
        data = self.request_data(request)

        username = data.get('username')
        password = data.get('password')

        if not username or not password:
            return self.api_error('Username or password not set', status=403)

        if core_utils.login_attempts_exceeded(username):
            unlock_email = core_utils.unlock_account_email(username)

            raven_client.context.merge(raven_client.get_data_from_request(request))
            raven_client.captureMessage('Maximum login attempts reached',
                                        extra={'username': username, 'from': 'API', 'unlock_email': unlock_email},
                                        level='warning')

            return self.api_error('You have reached the maximum login attempts.\nPlease try again later.', status=403)

        if '@' in username:
            try:
                username = User.objects.get(email__iexact=username).username
            except:
                return self.api_error('Unvalide email or password')

        user = authenticate(username=username, password=password)
        if user is not None:
            if user.is_active:
                if request.user.is_authenticated():
                    if user != request.user:
                        user_logout(request)
                        user_login(request, user)
                else:
                    user_login(request, user)

                token = user.get_access_token()

                return JsonResponse({
                    'token': token,
                    'user': {
                        'id': user.id,
                        'username': user.username,
                        'email': user.email
                    }
                }, safe=False)

        return self.api_error('Unvalide username or password')

    def get_all_stores(self, request, target, store_type, version):
        stores = []
        user = self.get_user(request, assert_login=True)
        for i in user.profile.get_shopify_stores():
            stores.append({
                'id': i.id,
                'name': i.title,
                'type': 'shopify',
                'url': i.get_link(api=False)
            })

        for i in user.profile.get_chq_stores():
            stores.append({
                'id': i.id,
                'name': i.title,
                'type': 'chq',
                'url': i.get_admin_url()
            })

        return JsonResponse(stores, safe=False)
