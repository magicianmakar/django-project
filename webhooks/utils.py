import json

from django.http import HttpResponse
from django.views import View

from leadgalaxy.models import ShopifyStore, ShopifyProduct
from woocommerce_core.models import WooStore
from leadgalaxy.utils import webhook_token
from lib.exceptions import capture_message, capture_exception


class ShopifyWebhookMixing(View):
    http_method_names = ['get', 'post']

    def verify_shopify_webhook(self, request):
        token = request.GET['t']

        try:
            store = ShopifyStore.objects.get(id=request.GET['store'], is_active=True)

            if token != webhook_token(store.id):
                capture_message('Invalid Shopify Webhook Token', extra={
                    'current': token,
                    'correct': webhook_token(store.id)
                })
            else:
                return store

        except ShopifyStore.DoesNotExist:
            return None

    def post(self, request):
        self.store = self.verify_shopify_webhook(request)
        if self.store:
            try:
                self.shopify_data = json.loads(request.body)
            except:
                self.shopify_data = None

            try:
                self.process_webhook(self.store, self.shopify_data)
            except:
                capture_exception()

        return HttpResponse('ok')

    def get_product(self):
        return ShopifyProduct.objects.get(store=self.store, shopify_id=self.shopify_data['id'])

    def process_webhook(self, store, shopify_data):
        capture_message('process_webhook not implemented')
        raise NotImplementedError('process_webhook not implemented')


class WooWebhookProcessing(View):
    http_method_names = ['post']

    def verify_woo_webhook(self, request):
        try:
            store = WooStore.objects.get(store_hash=request.GET['store'], is_active=True)
            return store
        except WooStore.DoesNotExist:
            return None

    def post(self, request):
        self.store = self.verify_woo_webhook(request)

        if self.store:
            try:
                self.shopify_data = json.loads(request.body)
            except:
                self.shopify_data = None

            try:
                self.process_webhook(self.store, self.shopify_data)
            except:
                capture_exception()
        else:
            return HttpResponse(status=404)

        return HttpResponse('ok')
