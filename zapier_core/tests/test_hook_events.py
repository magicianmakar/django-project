import simplejson as json
import mock
import requests
from mock import patch, ANY

from django.test import TestCase, RequestFactory
from django.contrib.auth.models import User

from rest_hooks.models import Hook

from leadgalaxy.models import ShopifyProduct
from leadgalaxy.views import webhook
from leadgalaxy.tasks import manage_product_change
from leadgalaxy import utils
from product_alerts.models import ProductChange
from zapier_core.tasks import deliver_hook


def deliver_hook_callback(*args, **kwargs):
    deliver_hook(*kwargs['args'])


def manage_product_change_callback(*args, **kwargs):
    manage_product_change(*kwargs['args'])


class HookEventsTestCase(TestCase):
    fixtures = ['product_changes.json']

    def setUp(self):
        self.factory = RequestFactory()
        self.user = User.objects.get(pk=1)

    @mock.patch.object(deliver_hook, 'apply_async', side_effect=deliver_hook_callback)
    @patch('requests.post')
    def test_deliver_hook(self, requests_post, deliver):
        hook = Hook.objects.create(
            user=self.user,
            event='variant:quantity',
            target='TARGETURL',
        )
        product_change = ProductChange.objects.get(pk=4)
        product_data = product_change.product.retrieve()
        product_change.send_hook_event(product_data)
        requests_post.assert_called_once_with(
            url=hook.target,
            data=ANY,
            headers=ANY,
        )


    @mock.patch.object(deliver_hook, 'apply_async', side_effect=deliver_hook_callback)
    @patch('requests.post')
    def test_deliver_hook_alert(self, requests_post, deliver):
        hook = Hook.objects.create(
            user=self.user,
            event='alert_created',
            target='TARGETURL',
        )
        product_change = ProductChange.objects.get(pk=2)
        product_change.send_hook_event_alert()
        requests_post.assert_called_once_with(
            url=hook.target,
            data=ANY,
            headers=ANY,
        )


    @mock.patch.object(manage_product_change, 'apply_async', side_effect=manage_product_change_callback)
    @patch('zapier_core.tasks.deliver_hook.apply_async')
    def test_variant_price_changed(self, deliver_hook, manage):
        hook = Hook.objects.create(
            user=self.user,
            event='variant:price',
            target='TARGETURL',
        )

        product_changes = []
        product = ShopifyProduct.objects.get(pk=4)
        shopify_product = utils.get_shopify_product(product.store, product.shopify_id)
        variant = shopify_product['variants'][0]
        price = round(float(variant['price']), 2)
        
        new_value = price + 5
        old_value = price
        product_changes.append({
            'level': 'variant',
            'name': 'price',
            'sku': variant['sku'],
            'new_value': new_value,
            'old_value': old_value,
        })
        request = self.factory.post(
            '/webhook/price-monitor/product?product={}&dropified_type=shopify'.format(product.id),
            data=json.dumps(product_changes),
            content_type='application/json'
        )
        response = webhook(request, 'price-monitor', None)
        self.assertEqual(response.status_code, 200)
        product_change = ProductChange.objects.latest('id')
        deliver_hook.assert_called_once_with(args=[hook.target, ANY, None, hook.id])
