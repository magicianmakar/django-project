import simplejson as json
import mock
import requests

from django.test import TestCase, RequestFactory
from django.contrib.auth.models import User

from leadgalaxy.models import ShopifyProduct
from leadgalaxy.views import webhook
from leadgalaxy.tasks import manage_product_change
from leadgalaxy import utils
from commercehq_core.models import CommerceHQProduct
from product_alerts.models import ProductChange, ProductVariantPriceHistory
from product_alerts.managers import ProductChangeManager


def manage_product_change_callback(*args, **kwargs):
    manage_product_change(*kwargs['args'])


class ProductChangeManagerTestCase(TestCase):
    fixtures = ['product_changes.json']

    def setUp(self):
        self.factory = RequestFactory()
        self.user = User.objects.get(pk=1)

    def test_shopify_product_disappears(self):
        self.user.profile.config = json.dumps({"alert_product_disappears": "unpublish"})
        self.user.profile.save()
        product_change = ProductChange.objects.get(pk=1)
        manager = ProductChangeManager.initialize(product_change)
        result = manager.apply_changes()
        self.assertEqual(result['published'], False)

    def test_chq_product_disappears(self):
        self.user.profile.config = json.dumps({"alert_product_disappears": "unpublish"})
        self.user.profile.save()
        product_change = ProductChange.objects.get(pk=3)
        manager = ProductChangeManager.initialize(product_change)
        result = manager.apply_changes()
        self.assertEqual(result['is_draft'], True)

    def test_changes_map(self):
        product_change = ProductChange.objects.get(pk=1)
        manager = ProductChangeManager.initialize(product_change)
        changes_map = manager.changes_map()
        self.assertEqual(len(changes_map['availability']), 1)

    def test_get_shopify_variant(self):
        product_change = ProductChange.objects.get(pk=2)
        manager = ProductChangeManager.initialize(product_change)
        product_data = utils.get_shopify_product(product_change.shopify_product.store, product_change.shopify_product.shopify_id)
        result = manager.get_variant(product_data, manager.variant_changes[0])
        self.assertEqual(result, 0)

    def test_get_chq_variant(self):
        product_change = ProductChange.objects.get(pk=4)
        manager = ProductChangeManager.initialize(product_change)
        product_data = product_change.product.retrieve()
        result = manager.get_variant(product_data, manager.variant_changes[0])
        self.assertEqual(result, 0)

    @mock.patch.object(manage_product_change, 'apply_async', side_effect=manage_product_change_callback)
    def test_webhook_shopify_price_change(self, manage):
        self.user.profile.config = json.dumps({"alert_price_change": "update"})
        self.user.profile.save()

        product_changes = []
        product = ShopifyProduct.objects.get(pk=4)
        shopify_product = utils.get_shopify_product(product.store, product.shopify_id)
        variant = shopify_product['variants'][0]
        price = round(float(variant['price']), 2)

        # update price
        old_price = round(price - (price / 2.0), 2)
        update_endpoint = product.store.get_link('/admin/products/{}.json'.format(product.shopify_id), api=True)
        shopify_product['variants'][0]['price'] = old_price
        r = requests.put(update_endpoint, json={'product': shopify_product})
        self.assertTrue(r.ok)

        product_changes.append({
            'level': 'variant',
            'name': 'price',
            'sku': variant['sku'],
            'new_value': price,
            'old_value': old_price,
        })
        request = self.factory.post(
            '/webhook/price-monitor/product?product={}&dropified_type=shopify'.format(product.id),
            data=json.dumps(product_changes),
            content_type='application/json'
        )
        response = webhook(request, 'price-monitor', None)
        self.assertEqual(response.status_code, 200)
        shopify_product = utils.get_shopify_product(product.store, product.shopify_id)
        updated_variant = shopify_product['variants'][0]
        updated_price = round(float(updated_variant['price']), 2)

        # check if price was updated back
        self.assertEqual(updated_price, price)
        # check if price history was added
        history = ProductVariantPriceHistory.objects.filter(shopify_product=product, variant_id=shopify_product['variants'][0]['id']).first()
        self.assertIsNotNone(history)
        self.assertEqual(history.old_price, old_price)
        self.assertEqual(history.new_price, updated_price)

    @mock.patch.object(manage_product_change, 'apply_async', side_effect=manage_product_change_callback)
    def test_webhook_shopify_quantity_change(self, manage):
        self.user.profile.config = json.dumps({"alert_quantity_change": "update"})
        self.user.profile.save()

        product_changes = []
        product = ShopifyProduct.objects.get(pk=5)
        shopify_product = utils.get_shopify_product(product.store, product.shopify_id)
        variant = shopify_product['variants'][0]
        quantity = variant['inventory_quantity']

        # update quantity
        update_endpoint = product.store.get_link('/admin/products/{}.json'.format(product.shopify_id), api=True)
        shopify_product['variants'][0]['inventory_quantity'] = quantity + 10
        r = requests.put(update_endpoint, json={'product': shopify_product})
        self.assertTrue(r.ok)

        product_changes.append({
            'level': 'variant',
            'name': 'quantity',
            'sku': '14:29#RB black;200000858:100014128#100cm',
            'new_value': quantity,
            'old_value': quantity + 10,
        })
        request = self.factory.post(
            '/webhook/price-monitor/product?product={}&dropified_type=shopify'.format(product.id),
            data=json.dumps(product_changes),
            content_type='application/json'
        )
        response = webhook(request, 'price-monitor', None)
        self.assertEqual(response.status_code, 200)
        shopify_product = utils.get_shopify_product(product.store, product.shopify_id)
        updated_variant = shopify_product['variants'][0]
        updated_quantity = updated_variant['inventory_quantity']

        # check if quantity was updated back
        self.assertEqual(updated_quantity, quantity)

    @mock.patch.object(manage_product_change, 'apply_async', side_effect=manage_product_change_callback)
    def test_webhook_chq_price_change(self, manage):
        self.user.profile.config = json.dumps({"alert_price_change": "update"})
        self.user.profile.save()

        product_changes = []
        product = CommerceHQProduct.objects.get(pk=1)
        chq_product = product.retrieve()
        variant = chq_product['variants'][0]
        price = round(float(variant['price']), 2)

        # update price
        old_price = round(price - (price / 2.0), 2)
        chq_product['variants'][0]['price'] = old_price
        r = product.store.request.patch(
            url='{}/{}'.format(product.store.get_api_url('products'), product.source_id),
            json={'variants': chq_product['variants']}
        )
        self.assertTrue(r.ok)

        product_changes.append({
            'level': 'variant',
            'name': 'price',
            'sku': '14:29#RB black;200000858:100014128#100cm',
            'new_value': price,
            'old_value': old_price,
        })
        request = self.factory.post(
            '/webhook/price-monitor/product?product={}&dropified_type=chq'.format(product.id),
            data=json.dumps(product_changes),
            content_type='application/json'
        )
        response = webhook(request, 'price-monitor', None)
        self.assertEqual(response.status_code, 200)
        chq_product = product.retrieve()
        updated_variant = chq_product['variants'][0]
        updated_price = round(float(updated_variant['price']), 2)

        # check if price was updated back
        self.assertEqual(updated_price, price)
        # check if price history was added
        history = ProductVariantPriceHistory.objects.filter(chq_product=product, variant_id=chq_product['variants'][0]['id']).first()
        self.assertIsNotNone(history)
        self.assertEqual(history.old_price, old_price)
        self.assertEqual(history.new_price, updated_price)
