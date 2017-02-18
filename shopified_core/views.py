import traceback

from django.views.generic import View
from django.conf import settings

from leadgalaxy.api import ShopifyStoreApi
from .mixins import ApiResponseMixin


class ShopifiedApi(ApiResponseMixin, View):
    supported_stores = [
        'all',      # Common endpoint
        'shopify',  # Shopify Stores
        'chq'       # CommerceHQ Stores
    ]

    def dispatch(self, request, *args, **kwargs):
        try:
            if kwargs['store_type'] not in self.supported_stores:
                return self.http_method_not_allowed(request, *args, **kwargs)

            method_name = self.method_name(request.method, kwargs['store_type'], kwargs['target'])
            handler = getattr(self, method_name, None)

            if handler:
                return handler(request, **kwargs)

            if kwargs['store_type'] == 'shopify':
                return ShopifyStoreApi.as_view()(request, *args, **kwargs)
        except:
            if settings.DEBUG:
                traceback.print_exc()

            raise

    def get_all_stores(self, request, target, store_type, version):
        pass
