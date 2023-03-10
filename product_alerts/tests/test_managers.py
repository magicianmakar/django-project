from unittest.mock import patch

import simplejson as json
import requests

from django.test import RequestFactory, tag
from django.contrib.auth.models import User

from lib.test import BaseTestCase
from leadgalaxy.models import ShopifyProduct, PriceMarkupRule
from webhooks.views import price_monitor_webhook
from leadgalaxy.tasks import manage_product_change
from leadgalaxy import utils
from commercehq_core.models import CommerceHQProduct
from groovekart_core.models import GrooveKartProduct
from woocommerce_core.models import WooProduct
from bigcommerce_core.models import BigCommerceProduct
from product_alerts.models import ProductChange
from product_alerts.managers import ProductChangeManager


def clamp(minvalue, value, maxvalue):
    return max(minvalue, min(value, maxvalue))


def manage_product_change_callback(*args, **kwargs):
    manage_product_change(*kwargs['args'])


class ProductChangeManagerTestCase(BaseTestCase):
    fixtures = ['product_changes.json']

    def setUp(self):
        self.factory = RequestFactory()
        self.user = User.objects.get(pk=1)

    @tag('slow')
    def test_shopify_product_disappears(self):
        self.user.profile.config = json.dumps({"alert_product_disappears": "unpublish"})
        self.user.profile.save()
        product_change = ProductChange.objects.get(pk=1)
        manager = ProductChangeManager.initialize(product_change)
        result = manager.apply_changes()
        self.assertEqual(result['published'], False)

    @tag('slow')
    @tag('excessive')
    def test_chq_product_disappears(self):
        self.user.profile.config = json.dumps({"alert_product_disappears": "unpublish"})
        self.user.profile.save()
        product_change = ProductChange.objects.get(pk=3)
        manager = ProductChangeManager.initialize(product_change)
        result = manager.apply_changes()
        self.assertEqual(result['published'], False)

    @tag('slow')
    def test_gkart_product_disappears(self):
        self.user.profile.config = json.dumps({"alert_product_disappears": "unpublish"})
        self.user.profile.save()
        product_change = ProductChange.objects.get(pk=5)
        manager = ProductChangeManager.initialize(product_change)
        result = manager.apply_changes()
        self.assertEqual(result['published'], False)

    @tag('slow')
    def test_woo_product_disappears(self):
        self.user.profile.config = json.dumps({"alert_product_disappears": "unpublish"})
        self.user.profile.save()
        product_change = ProductChange.objects.get(pk=7)
        manager = ProductChangeManager.initialize(product_change)
        result = manager.apply_changes()
        self.assertEqual(result['published'], False)

    @tag('slow')
    def test_bigcommerce_product_disappears(self):
        self.user.profile.config = json.dumps({"alert_product_disappears": "unpublish"})
        self.user.profile.save()
        product_change = ProductChange.objects.get(pk=8)
        manager = ProductChangeManager.initialize(product_change)
        result = manager.apply_changes()
        self.assertEqual(result['published'], False)

    def test_changes_map(self):
        product_change = ProductChange.objects.get(pk=1)
        manager = ProductChangeManager.initialize(product_change)
        changes_map = manager.changes_map()
        self.assertEqual(len(changes_map['availability']), 1)

    def test_changes_map_gkart(self):
        product_change = ProductChange.objects.get(pk=6)
        manager = ProductChangeManager.initialize(product_change)
        changes_map = manager.changes_map()
        self.assertEqual(len(changes_map['availability']), 1)

    def test_changes_map_woo(self):
        product_change = ProductChange.objects.get(pk=7)
        manager = ProductChangeManager.initialize(product_change)
        changes_map = manager.changes_map()
        self.assertEqual(len(changes_map['availability']), 1)

    def test_changes_map_bigcommerce(self):
        product_change = ProductChange.objects.get(pk=8)
        manager = ProductChangeManager.initialize(product_change)
        changes_map = manager.changes_map()
        self.assertEqual(len(changes_map['availability']), 1)

    @tag('slow')
    def test_get_shopify_variant(self):
        product_change = ProductChange.objects.get(pk=2)
        manager = ProductChangeManager.initialize(product_change)
        product_data = utils.get_shopify_product(product_change.shopify_product.store, product_change.shopify_product.shopify_id)
        if 'id' not in product_data['variants'][0]:
            return

        idx = manager.get_variant(product_data, manager.variant_changes[0])
        self.assertEqual(idx, 0)

    @tag('slow')
    @tag('excessive')
    def test_get_chq_variant(self):
        product_change = ProductChange.objects.get(pk=4)
        manager = ProductChangeManager.initialize(product_change)
        product_data = product_change.product.retrieve()
        idx = manager.get_variant(product_data, manager.variant_changes[0])
        self.assertEqual(idx, 0)

    @tag('slow')
    def test_get_woo_variant(self):
        product_change = ProductChange.objects.get(pk=7)
        manager = ProductChangeManager.initialize(product_change)
        product_data = product_change.product.retrieve()
        idx = manager.get_variant(product_data, manager.variant_changes[0])
        self.assertEqual(idx, 5)

    @tag('slow')
    def test_get_bigcommerce_variant(self):
        product_change = ProductChange.objects.get(pk=8)
        manager = ProductChangeManager.initialize(product_change)
        product_data = product_change.product.retrieve()
        if product_data:
            idx = manager.get_variant(product_data, manager.variant_changes[0])
            self.assertEqual(idx, 6)

    @tag('slow')
    @patch.object(manage_product_change, 'apply_async', side_effect=manage_product_change_callback)
    def test_webhook_shopify_price_change(self, manage):
        self.user.profile.config = json.dumps({"alert_price_change": "update"})
        self.user.profile.save()

        product_changes = []
        product = ShopifyProduct.objects.get(pk=4)
        shopify_product = utils.get_shopify_product(product.store, product.shopify_id)
        variant = shopify_product['variants'][0]
        if 'price' not in variant:
            return

        price = round(float(variant['price']), 2)

        # update price
        old_price = round(price - (price / 2.0), 2)
        old_compare_price = round(price - (price / 2.0), 2) * 2.0

        update_endpoint = product.store.api('products', product.shopify_id)
        shopify_product['variants'][0]['price'] = old_price
        shopify_product['variants'][0]['compare_at_price'] = old_compare_price
        r = requests.put(update_endpoint, json={'product': shopify_product})
        self.assertTrue(r.ok)

        new_value = round(price / 3.0, 2)
        old_value = round(old_price / 3.0, 2)
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
        response = price_monitor_webhook(request)
        self.assertEqual(response.status_code, 200)
        shopify_product = utils.get_shopify_product(product.store, product.shopify_id)
        updated_variant = shopify_product['variants'][0]
        updated_price = round(float(updated_variant['price']), 2)
        updated_compare_price = round(float(updated_variant['compare_at_price']), 2)

        # check if price was updated back and preserved the margin
        self.assertEqual(updated_price, round((old_price * new_value) / old_value, 2))
        self.assertEqual(updated_compare_price, round((old_compare_price * new_value) / old_value, 2))

    @tag('slow')
    @patch.object(manage_product_change, 'apply_async', side_effect=manage_product_change_callback)
    def test_webhook_shopify_price_change_global_markup(self, manage):
        auto_margin = 50
        auto_compare_at = 100
        auto_margin_cents = 99
        auto_compare_at_cents = 99
        self.user.profile.config = json.dumps({
            "alert_price_change": "update",
            "price_update_method": "global_markup",
            "auto_margin": "{}%".format(auto_margin),
            "auto_compare_at": "{}%".format(auto_compare_at),
            "auto_margin_cents": "{}".format(auto_margin_cents),
            "auto_compare_at_cents": "{}".format(auto_compare_at_cents),
        })
        self.user.profile.save()

        product_changes = []
        product = ShopifyProduct.objects.get(pk=4)
        shopify_product = utils.get_shopify_product(product.store, product.shopify_id)
        variant = shopify_product['variants'][0]
        if 'price' not in variant:
            return

        price = round(float(variant['price']), 2)

        new_value = round(price * 100.0 / (100 + auto_margin), 2)
        old_value = price  # not used in global markup update method
        product_changes.append({
            'level': 'variant',
            'name': 'price',
            'sku': variant['sku'],
            'new_value': new_value,
            'old_value': old_value
        })
        request = self.factory.post(
            '/webhook/price-monitor/product?product={}&dropified_type=shopify'.format(product.id),
            data=json.dumps(product_changes),
            content_type='application/json'
        )
        response = price_monitor_webhook(request)
        self.assertEqual(response.status_code, 200)
        shopify_product = utils.get_shopify_product(product.store, product.shopify_id)
        updated_variant = shopify_product['variants'][0]
        updated_price = round(float(updated_variant['price']), 2)
        updated_compare_price = round(float(updated_variant['compare_at_price']), 2)

        # check if price was updated back and preserved the margin
        new_price = float(str(int(new_value * (100 + auto_margin) / 100.0)) + '.' + str(auto_margin_cents))
        new_compare_price = float(str(int(new_value * (100 + auto_compare_at) / 100.0)) + '.' + str(auto_compare_at_cents))
        self.assertEqual(updated_price, new_price)
        self.assertEqual(updated_compare_price, new_compare_price)

    @tag('slow')
    @patch.object(manage_product_change, 'apply_async', side_effect=manage_product_change_callback)
    def test_webhook_shopify_price_change_custom_markup(self, manage):
        auto_margin = 50
        auto_compare_at = 100
        auto_margin_cents = 99
        auto_compare_at_cents = 99
        self.user.profile.config = json.dumps({
            "alert_price_change": "update",
            "price_update_method": "custom_markup",
            "auto_margin_cents": "{}".format(auto_margin_cents),
            "auto_compare_at_cents": "{}".format(auto_compare_at_cents),
        })
        self.user.profile.save()

        product_changes = []
        product = ShopifyProduct.objects.get(pk=4)
        shopify_product = utils.get_shopify_product(product.store, product.shopify_id)
        variant = shopify_product['variants'][0]
        if 'price' not in variant:
            return

        price = round(float(variant['price']), 2)

        new_value = round(price - auto_margin, 2)
        old_value = price  # not used in global markup update method

        # create a markup rule
        PriceMarkupRule.objects.create(
            user=self.user,
            name='',
            min_price=new_value - 1,
            max_price=new_value + 1,
            markup_value=auto_margin,
            markup_compare_value=auto_compare_at,
            markup_type='margin_amount',
        )

        product_changes.append({
            'level': 'variant',
            'name': 'price',
            'sku': variant['sku'],
            'new_value': new_value,
            'old_value': old_value
        })
        request = self.factory.post(
            '/webhook/price-monitor/product?product={}&dropified_type=shopify'.format(product.id),
            data=json.dumps(product_changes),
            content_type='application/json'
        )
        response = price_monitor_webhook(request)
        self.assertEqual(response.status_code, 200)
        shopify_product = utils.get_shopify_product(product.store, product.shopify_id)
        updated_variant = shopify_product['variants'][0]
        updated_price = round(float(updated_variant['price']), 2)
        updated_compare_price = round(float(updated_variant['compare_at_price']), 2)

        # check if price was updated back and preserved the margin
        new_price = float(str(int(new_value + auto_margin)) + '.' + str(auto_margin_cents))
        new_compare_price = float(str(int(new_value + auto_compare_at)) + '.' + str(auto_compare_at_cents))
        self.assertEqual(updated_price, new_price)
        self.assertEqual(updated_compare_price, new_compare_price)

    @tag('slow')
    @patch.object(manage_product_change, 'apply_async', side_effect=manage_product_change_callback)
    def test_webhook_shopify_quantity_change(self, manage):
        self.user.profile.config = json.dumps({"alert_quantity_change": "update"})
        self.user.profile.save()

        product_changes = []
        product = ShopifyProduct.objects.get(pk=5)
        shopify_product = utils.get_shopify_product(product.store, product.shopify_id)
        variant = shopify_product['variants'][0]
        if 'id' not in variant:
            return

        quantity = product.get_variant_quantity(variant=variant)

        # update quantity
        r = product.set_variant_quantity(quantity + 10, variant=shopify_product['variants'][0])
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

        response = price_monitor_webhook(request)
        self.assertEqual(response.status_code, 200)

        updated_quantity = product.get_variant_quantity(variant_id=shopify_product['variants'][0]['id'])

        # check if quantity was updated back
        self.assertEqual(updated_quantity, quantity)

    @tag('slow')
    @tag('excessive')
    @patch.object(manage_product_change, 'apply_async', side_effect=manage_product_change_callback)
    def test_webhook_chq_price_change(self, manage):
        self.user.profile.config = json.dumps({"alert_price_change": "update"})
        self.user.profile.save()

        product_changes = []
        product = CommerceHQProduct.objects.get(pk=1)
        chq_product = product.retrieve()
        variant = chq_product['variants'][0]
        if 'price' not in variant:
            return

        price = round(float(variant['price']), 2)

        # Reset price to a reasonable amount
        price = clamp(10.0, price, 100.0)

        # update price
        old_price = round(price - (price / 2.0), 2)
        chq_product['variants'][0]['price'] = old_price
        chq_product['variants'][0]['compare_price'] = old_price
        r = product.store.request.patch(
            url='{}/{}'.format(product.store.get_api_url('products'), product.source_id),
            json={'variants': chq_product['variants']}
        )
        self.assertTrue(r.ok)

        new_value = round(price / 3.0, 2)
        old_value = round(old_price / 3.0, 2)
        product_changes.append({
            'level': 'variant',
            'name': 'price',
            'sku': '14:29#RB black;200000858:100014128#100cm',
            'new_value': new_value,
            'old_value': old_value,
        })
        request = self.factory.post(
            '/webhook/price-monitor/product?product={}&dropified_type=chq'.format(product.id),
            data=json.dumps(product_changes),
            content_type='application/json'
        )
        response = price_monitor_webhook(request)
        self.assertEqual(response.status_code, 200)
        chq_product = product.retrieve()

        updated_variant = chq_product['variants'][0]
        updated_price = round(float(updated_variant['price']), 2)

        # check if price was updated back and preserved the margin
        self.assertEqual(updated_price, round(old_price * new_value / old_value, 2))

    @tag('slow')
    @patch.object(manage_product_change, 'apply_async', side_effect=manage_product_change_callback)
    def test_webhook_gkart_price_change_no_variant(self, manage):
        self.user.profile.config = json.dumps({"alert_price_change": "update"})
        self.user.profile.save()

        product_changes = []
        product = GrooveKartProduct.objects.get(pk=16)
        gkart_product = product.retrieve()

        price = round(float(gkart_product['price']), 2)

        # Reset price to a reasonable amount
        price = clamp(10.0, price, 100.0)

        # update price
        old_price = round(price - (price / 2.0), 2)
        api_endpoint = product.store.get_api_url('products.json')
        r = product.store.request.post(api_endpoint, json={
            'product': {
                'action': 'update_product',
                'id': product.source_id,
                'price': old_price,
                'compare_default_price': old_price,
            },
        })
        self.assertTrue(r.ok)

        new_value = round(price / 3.0, 2)
        old_value = round(old_price / 3.0, 2)
        product_changes.append({
            'level': 'variant',
            'name': 'price',
            'new_value': new_value,
            'old_value': old_value,
            'sku': '200000182:193#Single Len DVR;200009160:100018900#DVR with 16G TF card',
        })
        request = self.factory.post(
            '/webhook/price-monitor/product?product={}&dropified_type=gkart'.format(product.id),
            data=json.dumps(product_changes),
            content_type='application/json'
        )
        response = price_monitor_webhook(request)
        self.assertEqual(response.status_code, 200)
        gkart_product = product.retrieve()

        updated_price = round(float(gkart_product['price']), 2)

        # check if price was updated back and preserved the margin
        self.assertEqual(updated_price, round(old_price * new_value / old_value, 2))

    @tag('slow')
    @patch.object(manage_product_change, 'apply_async', side_effect=manage_product_change_callback)
    def test_webhook_gkart_price_change(self, manage):
        self.user.profile.config = json.dumps({"alert_price_change": "update"})
        self.user.profile.save()

        product_changes = []
        product = GrooveKartProduct.objects.get(pk=17)
        gkart_product = product.retrieve()
        variant = gkart_product['variants'][0]
        if 'price' not in variant:
            return

        price = round(float(variant['price']), 2)

        # Reset price to a reasonable amount
        price = clamp(10.0, price, 100.0)

        # update price
        old_price = round(price - (price / 2.0), 2)
        api_endpoint = product.store.get_api_url('variants.json')
        r = product.store.request.post(api_endpoint, json={
            'action': 'update',
            'product_id': product.source_id,
            'variants': [
                {
                    'id': variant['id_product_variant'],
                    'price': old_price,
                    'compare_at_price': old_price
                }
            ]
        })
        self.assertTrue(r.ok)

        new_value = round(price / 3.0, 2)
        old_value = round(old_price / 3.0, 2)
        product_changes.append({
            'level': 'variant',
            'name': 'price',
            'sku': '200000182:193#Single Len DVR;200009160:100018900#DVR with 16G TF card',
            'new_value': new_value,
            'old_value': old_value,
        })
        request = self.factory.post(
            '/webhook/price-monitor/product?product={}&dropified_type=gkart'.format(product.id),
            data=json.dumps(product_changes),
            content_type='application/json'
        )
        response = price_monitor_webhook(request)
        self.assertEqual(response.status_code, 200)
        gkart_product = product.retrieve()

        updated_variant = gkart_product['variants'][0]
        updated_price = round(float(updated_variant['price']), 2)

        # check if price was updated back and preserved the margin
        self.assertEqual(updated_price, round(old_price * new_value / old_value, 2))

    @tag('slow')
    @patch.object(manage_product_change, 'apply_async', side_effect=manage_product_change_callback)
    def test_webhook_woo_price_change(self, manage):
        self.user.profile.config = json.dumps({"alert_price_change": "update"})
        self.user.profile.save()

        product_changes = []
        product = WooProduct.objects.get(pk=1)
        woo_product = product.retrieve()
        variant = woo_product['variants'][0]
        if 'regular_price' not in variant:
            return

        price = round(float(variant['regular_price']), 2)

        # Reset price to a reasonable amount
        price = clamp(10.0, price, 100.0)

        # update price
        old_price = round(price - (price / 2.0), 2)
        api_endpoint = 'products/{}/variations/batch'.format(product.source_id)
        r = product.store.wcapi.put(api_endpoint, {
            'update': [
                {
                    'id': variant['id'],
                    'sale_price': old_price,
                    'regular_price': old_price,
                }
            ],
        })
        self.assertTrue(r.ok)

        new_value = round(price / 3.0, 2)
        old_value = round(old_price / 3.0, 2)
        product_changes.append({
            'level': 'variant',
            'name': 'price',
            'sku': '200000182:691#Double Lens DVR;200009160:350525#DVR without TF card',
            'new_value': new_value,
            'old_value': old_value,
        })
        request = self.factory.post(
            '/webhook/price-monitor/product?product={}&dropified_type=woo'.format(product.id),
            data=json.dumps(product_changes),
            content_type='application/json'
        )
        response = price_monitor_webhook(request)
        self.assertEqual(response.status_code, 200)
        woo_product = product.retrieve()

        updated_variant = woo_product['variants'][0]
        updated_price = round(float(updated_variant['regular_price']), 2)

        # check if price was updated back and preserved the margin
        self.assertEqual(updated_price, round(old_price * new_value / old_value, 2))

    @tag('slow')
    @patch.object(manage_product_change, 'apply_async', side_effect=manage_product_change_callback)
    def test_webhook_bigcommerce_price_change_no_variant(self, manage):
        self.user.profile.config = json.dumps({"alert_price_change": "update"})
        self.user.profile.save()

        product_changes = []
        product = BigCommerceProduct.objects.get(pk=2)
        bigcommerce_product = product.retrieve()
        if not bigcommerce_product:
            return

        price = round(float(bigcommerce_product['price']), 2)

        # Reset price to a reasonable amount
        price = clamp(10.0, price, 100.0)

        # update price
        old_price = round(price - (price / 2.0), 2)
        r = product.store.request.put(
            url=product.store.get_api_url('v3/catalog/products/%s' % product.source_id),
            json={
                'price': old_price
            }
        )
        self.assertTrue(r.ok)

        new_value = round(price / 3.0, 2)
        old_value = round(old_price / 3.0, 2)
        product_changes.append({
            'level': 'variant',
            'name': 'price',
            'new_value': new_value,
            'old_value': old_value,
        })
        request = self.factory.post(
            '/webhook/price-monitor/product?product={}&dropified_type=bigcommerce'.format(product.id),
            data=json.dumps(product_changes),
            content_type='application/json'
        )
        response = price_monitor_webhook(request)
        self.assertEqual(response.status_code, 200)
        bigcommerce_product = product.retrieve()

        updated_price = round(float(bigcommerce_product['price']), 2)

        # check if price was updated back and preserved the margin
        self.assertEqual(updated_price, round(old_price * new_value / old_value, 2))

    @tag('slow')
    @patch.object(manage_product_change, 'apply_async', side_effect=manage_product_change_callback)
    def test_webhook_bigcommerce_price_change(self, manage):
        self.user.profile.config = json.dumps({"alert_price_change": "update"})
        self.user.profile.save()

        product_changes = []
        product = BigCommerceProduct.objects.get(pk=1)
        bigcommerce_product = product.retrieve()
        if not bigcommerce_product:
            return

        variant = bigcommerce_product['variants'][0]
        if 'price' not in variant:
            return

        price = round(float(variant['price']), 2)

        # Reset price to a reasonable amount
        price = clamp(10.0, price, 100.0)

        # update price
        old_price = round(price - (price / 2.0), 2)
        r = product.store.request.put(
            url=product.store.get_api_url('v3/catalog/products/%s/variants/%s' % (product.source_id, variant['id'])),
            json={
                'price': old_price,
                'sale_price': old_price,
            }
        )
        self.assertTrue(r.ok)

        new_value = round(price / 3.0, 2)
        old_value = round(old_price / 3.0, 2)
        product_changes.append({
            'level': 'variant',
            'name': 'price',
            'sku': '200000182:29#Double Lens DVR-10M;200009160:100018900#16G',
            'new_value': new_value,
            'old_value': old_value,
        })
        request = self.factory.post(
            '/webhook/price-monitor/product?product={}&dropified_type=bigcommerce'.format(product.id),
            data=json.dumps(product_changes),
            content_type='application/json'
        )
        response = price_monitor_webhook(request)
        self.assertEqual(response.status_code, 200)
        bigcommerce_product = product.retrieve()

        updated_variant = bigcommerce_product['variants'][0]
        updated_price = round(float(updated_variant['price']), 2)

        # check if price was updated back and preserved the margin
        self.assertEqual(updated_price, round(old_price * new_value / old_value, 2))
