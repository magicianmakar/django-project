from django.utils.module_loading import import_string

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.db.models import ObjectDoesNotExist
from django.views.generic import View

import requests
from lib.exceptions import capture_exception, capture_message

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

        for name, module in list(settings.DROPIFIED_API.items()):
            self.loaded_api[name] = import_string(module)
            self.supported_stores.append(name)

            if not issubclass(self.loaded_api[name], ApiResponseMixin):
                print('WARNING: API Module', module, 'does not use ApiResponseMixin')

    def dispatch(self, request, *args, **kwargs):
        if not hasattr(self, 'loaded_api'):
            self._load_api()

        for k, v in list(self.default.items()):
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
                if request.method != 'OPTIONS':
                    capture_message('Unsupported Request Method', extra={'method': request.method})

                return self.http_method_not_allowed(request, *args, **kwargs)

            # Do we have this method in our 'all' APIs?
            method_name = self.method_name(request.method, kwargs['target'])
            if getattr(self.loaded_api['all'], method_name, None):
                return self.loaded_api['all'].as_view()(request, *args, **kwargs)

            if store_type in self.loaded_api:
                return self.loaded_api[store_type].as_view()(request, *args, **kwargs)

            raise Exception("Unknown Store Type")

        except PermissionDenied as e:
            reason = str(e) if str(e) else "You don't have permission to perform this action"
            return self.api_error('Permission Denied: %s' % reason, status=403)

        except ObjectDoesNotExist:
            capture_exception(level='warning')
            return self.api_error('Requested resource not found', status=404)

        except requests.Timeout:
            capture_exception()
            return self.api_error('API Request Timeout', status=501)

        except ApiLoginException as e:
            return self.api_error(e.description(), status=401)

        except:
            capture_exception()

            return self.api_error('Internal Server Error')
