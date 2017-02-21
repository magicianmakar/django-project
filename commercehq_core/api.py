from django.conf import settings
from django.views.generic import View

from raven.contrib.django.raven_compat.models import client as raven_client

from shopified_core.mixins import ApiResponseMixin

import tasks


class CHQStoreApi(ApiResponseMixin, View):
    http_method_names = ['get', 'post', 'delete']

    def dispatch(self, request, *args, **kwargs):
        if request.method.lower() not in self.http_method_names:
            raven_client.captureMessage('Unsupported Request Method', extra={'method': request.method})
            return self.http_method_not_allowed(request, *args, **kwargs)

        return self.proccess_api(request, **kwargs)

    def proccess_api(self, request, target, store_type, version):
        self.target = target
        self.data = self.request_data(request)

        user = self.get_user(request)
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
            if settings.DEBUG:
                print 'Method Not Found:', method_name

            raven_client.captureMessage('Non-handled endpoint', extra={'method': method_name})
            return self.api_error('Non-handled endpoint', status=405)

        res = handler(request, user, self.data)
        if res is None:
            res = self.response

        if res is None:
            raven_client.captureMessage('API Response is empty')
            res = self.api_error('zInternal Server Error', 500)

        return res

    def post_save_for_later(self, request, user, data):
        return self.api_success(tasks.save_for_later(data, user.id))
