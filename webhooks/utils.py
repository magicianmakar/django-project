import base64
import hmac
import json
from hashlib import sha256

from django.conf import settings
from django.http import HttpResponse
from django.views import View

from leadgalaxy.models import ShopifyStore, ShopifyProduct
from woocommerce_core.models import WooStore
from leadgalaxy.utils import webhook_token
from lib.exceptions import capture_message, capture_exception


class ShopifyWebhookVerifyMixing:
    http_method_names = ['get', 'post']

    def verify_shopify_webhook_signature(store, request, throw_excption=True):
        api_data = request.body
        request_hash = request.META.get('HTTP_X_SHOPIFY_HMAC_SHA256')
        shop = request.META.get('HTTP_X_SHOPIFY_SHOP_DOMAIN')

        webhook_hash = hmac.new(settings.SHOPIFY_API_SECRET.encode(), api_data, sha256).digest()
        webhook_hash = base64.b64encode(webhook_hash).decode()

        if webhook_hash == request_hash:
            if shop:
                return shop
            else:
                raise Exception('Shop domain not found in header')
        else:
            raise Exception('Invalid signature')


class ShopifyWebhookMixing(View):
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
