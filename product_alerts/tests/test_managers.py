import simplejson as json
import mock
import requests

from django.test import RequestFactory, tag
from django.contrib.auth.models import User

from lib.test import BaseTestCase
from leadgalaxy.models import ShopifyProduct, PriceMarkupRule
from leadgalaxy.views import webhook
from leadgalaxy.tasks import manage_product_change
from leadgalaxy import utils
from commercehq_core.models import CommerceHQProduct
from product_alerts.models import ProductChange, ProductVariantPriceHistory
from product_alerts.managers import ProductChangeManager


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

    @tag('slow')
    def test_get_shopify_variant(self):
        product_change = ProductChange.objects.get(pk=2)
        manager = ProductChangeManager.initialize(product_change)
        product_data = utils.get_shopify_product(product_change.shopify_product.store, product_change.shopify_product.shopify_id)
        result = manager.get_variant(product_data, manager.variant_changes[0])
        self.assertEqual(result, 0)

    @tag('slow')
    def test_get_chq_variant(self):
        product_change = ProductChange.objects.get(pk=4)
        manager = ProductChangeManager.initialize(product_change)
        product_data = product_change.product.retrieve()
        result = manager.get_variant(product_data, manager.variant_changes[0])
        self.assertEqual(result, 0)

    @tag('slow')
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
        old_compare_price = round(price - (price / 2.0), 2) * 2.0

        update_endpoint = product.store.get_link('/admin/products/{}.json'.format(product.shopify_id), api=True)
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
        response = webhook(request, 'price-monitor', None)
        self.assertEqual(response.status_code, 200)
        shopify_product = utils.get_shopify_product(product.store, product.shopify_id)
        updated_variant = shopify_product['variants'][0]
        updated_price = round(float(updated_variant['price']), 2)
        updated_compare_price = round(float(updated_variant['compare_at_price']), 2)

        # check if price was updated back and preserved the margin
        self.assertEqual(updated_price, round((old_price * new_value) / old_value, 2))
        self.assertEqual(updated_compare_price, round((old_compare_price * new_value) / old_value, 2))

        # check if price history was added
        history = ProductVariantPriceHistory.objects.filter(shopify_product=product, variant_id=shopify_product['variants'][0]['id']).first()
        self.assertIsNotNone(history)
        self.assertEqual(history.old_price, old_value)
        self.assertEqual(history.new_price, new_value)

    @tag('slow')
    @mock.patch.object(manage_product_change, 'apply_async', side_effect=manage_product_change_callback)
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
        response = webhook(request, 'price-monitor', None)
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

        # check if price history was added
        history = ProductVariantPriceHistory.objects.filter(shopify_product=product, variant_id=shopify_product['variants'][0]['id']).first()
        self.assertIsNotNone(history)
        self.assertEqual(history.old_price, old_value)
        self.assertEqual(history.new_price, new_value)

    @tag('slow')
    @mock.patch.object(manage_product_change, 'apply_async', side_effect=manage_product_change_callback)
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
        price = round(float(variant['price']), 2)

        new_value = round(price - auto_margin, 2)
        old_value = price  # not used in global markup update method

        # create a markup rule
        markup_rule = PriceMarkupRule.objects.create(
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
        response = webhook(request, 'price-monitor', None)
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

        # check if price history was added
        history = ProductVariantPriceHistory.objects.filter(shopify_product=product, variant_id=shopify_product['variants'][0]['id']).first()
        self.assertIsNotNone(history)
        self.assertEqual(history.old_price, old_value)
        self.assertEqual(history.new_price, new_value)

    @tag('slow')
    @mock.patch.object(manage_product_change, 'apply_async', side_effect=manage_product_change_callback)
    def test_webhook_shopify_quantity_change(self, manage):
        self.user.profile.config = json.dumps({"alert_quantity_change": "update"})
        self.user.profile.save()

        product_changes = []
        product = ShopifyProduct.objects.get(pk=5)
        shopify_product = utils.get_shopify_product(product.store, product.shopify_id)
        variant = shopify_product['variants'][0]
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

        response = webhook(request, 'price-monitor', None)
        self.assertEqual(response.status_code, 200)

        updated_quantity = product.get_variant_quantity(variant_id=shopify_product['variants'][0]['id'])

        # check if quantity was updated back
        self.assertEqual(updated_quantity, quantity)

    @tag('slow')
    @mock.patch.object(manage_product_change, 'apply_async', side_effect=manage_product_change_callback)
    def test_webhook_chq_price_change(self, manage):
        self.user.profile.config = json.dumps({"alert_price_change": "update"})
        self.user.profile.save()

        product_changes = []
        product = CommerceHQProduct.objects.get(pk=1)
        chq_product = product.retrieve()
        variant = chq_product['variants'][0]
        price = round(float(variant['price']), 2)

        # Reset price to a reasonable amount
        price = 100.0 if price < 0.02 else price

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
        response = webhook(request, 'price-monitor', None)
        self.assertEqual(response.status_code, 200)
        chq_product = product.retrieve()
        updated_variant = chq_product['variants'][0]
        updated_price = round(float(updated_variant['price']), 2)

        # check if price was updated back and preserved the margin
        self.assertEqual(updated_price, round(old_price * new_value / old_value, 2))
        # check if price history was added
        history = ProductVariantPriceHistory.objects.filter(chq_product=product, variant_id=chq_product['variants'][0]['id']).first()
        self.assertIsNotNone(history)
        self.assertEqual(history.old_price, old_value)
        self.assertEqual(history.new_price, new_value)
