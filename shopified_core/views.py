from django.views.generic import View

from leadgalaxy.api import ShopifyStoreApi


class ShopifiedApi(View):
    supported_stores = ['shopify', 'chq']

    def dispatch(self, request, *args, **kwargs):
        if kwargs['store_type'] not in self.supported_stores:
            return self.http_method_not_allowed(request, *args, **kwargs)

        if kwargs['store_type'] == 'shopify':
            return ShopifyStoreApi.as_view()(request, *args, **kwargs)
