import traceback
from django.utils.module_loading import import_string

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.views.generic import View

import requests
from raven.contrib.django.raven_compat.models import client as raven_client

from .mixins import ApiResponseMixin
from .exceptions import ApiLoginException


class ShopifiedApiBase(ApiResponseMixin, View):
    http_method_names = ['GET', 'POST', 'DELETE']

    default = {
        'store_type': 'shopify',
        'version': 1
    }

    def _load_api(self):
        self.loaded_api = {}
        self.supported_stores = []

        for name, module in settings.DROPIFIED_API.items():
            self.loaded_api[name] = import_string(module)
            self.supported_stores.append(name)

            if not issubclass(self.loaded_api[name], ApiResponseMixin):
                print 'WARNING: API Module', module, 'does not use ApiResponseMixin'

    def dispatch(self, request, *args, **kwargs):
        if not hasattr(self, 'loaded_api'):
            self._load_api()

        for k, v in self.default.items():
            if not kwargs.get(k):
                kwargs[k] = v

        try:
            # Store Type is also the API namespace
            store_type = kwargs['store_type']

            # Check if this store type is supported
            if store_type not in self.supported_stores:
                return self.http_method_not_allowed(request, *args, **kwargs)

            # Check if HTTP request method is supported
            if request.method.upper() not in self.http_method_names:
                raven_client.captureMessage('Unsupported Request Method', extra={'method': request.method})
                return self.http_method_not_allowed(request, *args, **kwargs)

            # Do we have this method in our 'all' APIs?
            method_name = self.method_name(request.method, kwargs['target'])
            if getattr(self.loaded_api['all'], method_name, None):
                return self.loaded_api['all'].as_view()(request, *args, **kwargs)

            if store_type in self.loaded_api:
                return self.loaded_api[store_type].as_view()(request, *args, **kwargs)

            raise Exception("Unknown Store Type")

        except PermissionDenied as e:
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
