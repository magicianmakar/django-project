from django.http import JsonResponse
from django.contrib.auth.models import User

from raven.contrib.django.raven_compat.models import client as raven_client

from .exceptions import ApiLoginException


class ApiResponseMixin():
    response = None

    def api_error(self, description, status=500):
        self.response = JsonResponse({
            'error': description
        }, status=status)

        return self.response

    def api_success(self, rep=None, status=200):
        if rep is None:
            rep = {}

        rep.update({'status': 'ok'})

        self.response = JsonResponse(rep, status=status)

        return self.response

    def method_name(self, *args):
        return '_'.join([
            i.lower().replace('-', '_') for i in args
        ])

    def request_data(self, request):
        if request.method == 'POST':
            return request.POST
        elif request.method in ['GET', 'DELETE']:
            return request.GET

    def get_user(self, request, data=None, assert_login=False):
        """
            Return User from the current request data
        """

        user = None

        if data is None:
            data = self.request_data(request)

        authorization = request.META.get('HTTP_AUTHORIZATION')
        if authorization:
            if 'undefined' in authorization:
                authorization = None
            else:
                authorization = authorization.split(' ')
                if len(authorization) == 2:
                    authorization = authorization[1]
                else:
                    authorization = None

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

        if request.user.is_authenticated():
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
