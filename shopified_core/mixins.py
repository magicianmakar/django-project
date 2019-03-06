from django.http import JsonResponse
from django.contrib.auth.models import User
from raven.contrib.django.raven_compat.models import client as raven_client

import simplejson as json

from .exceptions import ApiLoginException


class ApiResponseMixin():
    response = None
    login_non_required = []

    def api_error(self, description, status=500):
        self.response = JsonResponse({
            'error': description
        }, status=status)

        return self.response

    def api_success(self, rep=None, status=200, safe=True):
        if rep is None:
            rep = {}

        if safe:
            rep.update({'status': 'ok'})

        self.response = JsonResponse(rep, status=status, safe=safe)

        return self.response

    def method_name(self, *args):
        return '_'.join([
            i.lower().replace('-', '_') for i in args
        ])

    def request_data(self, request):
        if request.method == 'POST':
            if request.POST:
                return request.POST
            else:
                if 'application/json' in request.META.get('CONTENT_TYPE', ''):
                    return json.loads(request.body)

        elif request.method in ['GET', 'DELETE']:
            return request.GET

    def get_user(self, request, data=None, assert_login=True):
        """
            Return User from the current request data
        """

        user = None

        if data is None:
            data = self.request_data(request) or {}

        authorization = request.META.get('HTTP_AUTHORIZATION') or request.GET.get('_t')
        if authorization:
            if 'undefined' in authorization:
                authorization = None
            else:
                authorization = authorization.split(' ')
                if len(authorization) == 2:
                    authorization = authorization[1]
                else:
                    authorization = authorization[0]

        if authorization or data.get('access_token'):
            token = authorization if authorization else data.get('access_token')
            user = self.user_from_token(token)

            if not user:
                raise ApiLoginException('unvalid_access_token')

            if token != authorization and not data.get('newrelic'):
                raven_client.captureMessage(
                    'Authorization Different From Access Token',
                    extra={
                        'aut': authorization,
                        'tok': token,
                        'vers': request.META.get('HTTP_X_EXTENSION_VERSION')
                    },
                    level='warning'
                )

        if request.user.is_authenticated:
            if user is None:
                user = request.user
            else:
                if user != request.user and not user.is_superuser:
                    if request.method != 'GET':
                        raven_client.captureMessage(
                            'Different account login',
                            extra={'Request User': request.user, 'API User': user},
                            level='warning'
                        )

                    raise ApiLoginException('different_account_login')

        if assert_login and not user:
            raise ApiLoginException('login_required')

        return user

    def user_from_token(self, token):
        if not token:
            return None

        try:
            user = User.objects.get(accesstoken__token=token)
        except User.DoesNotExist:
            return None
        except:
            raven_client.captureException()
            return None

        return user

    def dispatch(self, request, *args, **kwargs):
        if request.method.lower() not in self.http_method_names:
            if request.method != 'OPTIONS':
                raven_client.captureMessage('Unsupported Request Method', extra={'method': request.method})

            return self.http_method_not_allowed(request, *args, **kwargs)

        self.request_kwargs = kwargs

        return self.process_api(request, **kwargs)

    def process_api(self, request, target, store_type, version):
        self.target = target
        self.data = self.request_data(request)

        assert_login = target not in self.login_non_required

        user = self.get_user(request, assert_login=assert_login)
        if user:
            raven_client.user_context({
                'id': user.id,
                'username': user.username,
                'email': user.email
            })

            extension_version = request.META.get('HTTP_X_EXTENSION_VERSION')
            if extension_version:
                user.set_config('extension_version', extension_version)

        method_name = self.method_name(request.method, target)
        handler = getattr(self, method_name, None)

        if not handler:
            raven_client.captureMessage('Non-handled endpoint', extra={'method': method_name})
            return self.api_error('Non-handled endpoint', status=405)

        res = handler(request, user, self.data)
        if res is None:
            res = self.response

        if res is None:
            raven_client.captureMessage('API Response is empty')
            res = self.api_error('Internal Server Error', 500)

        return res
