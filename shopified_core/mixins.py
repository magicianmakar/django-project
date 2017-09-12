from django.http import JsonResponse
from django.contrib.auth.models import User

import simplejson as json

from raven.contrib.django.raven_compat.models import client as raven_client

from .exceptions import ApiLoginException


class ApiResponseMixin():
    response = None

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
        if request.user.is_authenticated():
            user = request.user

        if assert_login and not user:
            raise ApiLoginException('login_required')

        return user
