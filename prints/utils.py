import copy
import json
from decimal import Decimal, ROUND_HALF_UP, ROUND_DOWN

import requests
from django.conf import settings

from commercehq_core.api import CHQStoreApi
from commercehq_core.models import CommerceHQStore
from groovekart_core.api import GrooveKartApi
from groovekart_core.models import GrooveKartStore
from leadgalaxy.api import ShopifyStoreApi
from shopified_core.utils import safe_int
from woocommerce_core.api import WooStoreApi
from woocommerce_core.models import WooStore
from .models import Category, ProductPrice


def get_store_api(store):
    if isinstance(store, CommerceHQStore):
        return CHQStoreApi()
    elif isinstance(store, WooStore):
        return WooStoreApi()
    elif isinstance(store, GrooveKartStore):
        return GrooveKartApi()
    else:
        return ShopifyStoreApi()


class LayerApp(object):
    base_url = 'https://layerapp.com/productmaker'
    api_key = 'layer_dropify'
    access_token = '547fdf2d31af69c8fef0f80fccc445b016882ecd'

    def __get_url(self, url):
        if url.startswith('/'):
            url = url[1:]

        return f'{self.base_url}/{url}'

    def __get_base_params(self):
        return {
            'api_key': self.api_key,
            'access_token': self.access_token,
        }

    def get_categories(self):
        params = self.__get_base_params()
        params.update({
            'action': 'get_categories'
        })

        url = self.__get_url('/api')
        r = requests.post(url, json=params)
        return r.json()

    def get_products(self):
        params = self.__get_base_params()
        params.update({
            'action': 'products'
        })

        url = self.__get_url('/api')
        r = requests.post(url, json=params)
        return r.json()

    def product(self, product_id):
        params = self.__get_base_params()
        params.update({
            "action": "single_product",
            "product_id": product_id
        })

        url = self.__get_url('/api')
        result = requests.post(url, json=params).json()
        return result

    def generate_mockup(self, variant_id, first_image, second_image=None, paired=True):
        params = self.__get_base_params()
        if paired:
            params.update({
                "variant_id": str(variant_id),
                "left_img": first_image,
                "right_img": second_image
            })
        else:
            params.update({
                "variant_id": str(variant_id),
                "img": first_image
            })

        url = self.__get_url('/mockup_api')
        r = requests.post(url, json=params)
        result = r.json()

        mockup = result.get('mockup')
        if mockup:
            if not mockup.startswith('http'):
                mockup = f'https://{mockup}'

            return mockup

        return result

    def place_order(self, order):
        params = self.__get_base_params()
        params.update({
            "action": "create_order",
            "order": order.get_layerapp_dict()
        })

        if settings.LAYERAPP_TEST:
            params['order']['test'] = True
            params['order']['id'] = f"T-{params['order']['id']}"

        url = self.__get_url('/create_api_order')
        r = requests.post(url, json=params)
        return r.json()

    def is_authorized(self, api_data):
        api_key = api_data.get('api_key')
        access_token = api_data.get('access_token')
        if api_key != self.api_key or access_token != self.access_token:
            return False
        return True


def import_layerapp_product(product, api_product=None, verbosity=1):
    if api_product is None:
        layer_app = LayerApp()
        api_product = layer_app.product(product.source_id)

    api_product['original_data'] = copy.deepcopy(api_product)

    try:
        product_type = Category.objects.get(
            source_id=api_product.get('category_id'),
            source_type='layerapp'
        )
    except Category.DoesNotExist:
        product_type = None

    for v in api_product.get('variants', []):
        if v.get('variant_image'):
            image = v.get('variant_image')
            if not image.startswith('http'):
                image = f'https://{image}'
            v['variant_image'] = image

            if verbosity >= 2:
                r = requests.head(image)
                if r.status_code == 404:
                    print(f"Variant (ID:{v.get('id')}) image not found: {image}")

    image = api_product.get('product_image')
    if not image.startswith('http'):
        image = f'https://{image}'

    skus = [api_product.get('china_sku')]
    if 'usa_sku' in api_product:
        skus.append(api_product.get('usa_sku'))

    # Use prices from "Layer App Purchase Price" spreadsheet
    if 'price' in api_product:
        del api_product['price']

    if 'usa_price' in api_product:
        del api_product['usa_price']

    for k, size in api_product.get('sizes', []).items():
        if 'price' in size:
            del size['price']

        if 'usa_price' in size:
            del size['usa_price']

        if 'china_sku' in size:
            skus.append(size.get('china_sku'))

        if 'usa_sku' in size:
            skus.append(size.get('usa_sku'))

    # Update price-sku relation
    ProductPrice.objects.filter(product=product).update(product=None)
    prices = ProductPrice.objects.filter(sku__in=skus)
    prices.update(product=product)
    product.price_range = ','.join([str(p) for p in prices.values_list('target', flat=True)])
    product.price_range = generate_new_price_range(product)

    product.title = api_product.get('product_name')
    product.product_type = product_type
    product.default_image = image
    product.skus = ','.join(skus)
    product.source_data = json.dumps(api_product)
    product.save()


def place_order(order):
    layerapp = LayerApp()
    layerapp.place_order(order)

    line_items = order.line_items.all()
    return dict(
        order_id=order.order_id,
        line_id=','.join([str(i.line_id) for i in line_items]),
        store=order.object_id,
        source_id=order.order_name,
        combined=len(line_items) > 1,
        source_type='dropified-print',
    )


def get_tracking_details(order):
    status = f'D_{order.status.upper()}'
    return {
        'status': status,
        'orderStatus': status,  # Mock extension
        'tracking_number': order.tracking_number,
        'order_details': {'cost': {
            'total': str(order.total_amount),
            'products': str(order.total_amount),
            'shipping': '0.00',
        }},
        'bundle': False,
        'source_id': order.order_name,
    }


def generate_new_price_range(product, product_price=None):
    prices = [Decimal(p) for p in product.price_range.split(',') if p]
    if product_price is not None:
        prices.append(Decimal(product_price.target))

    prices = [p for p in prices if p > 0]
    if len(prices) == 0:
        return ''

    new_prices = set()
    new_prices.add(str(min(prices)))
    new_prices.add(str(max(prices)))
    return ','.join(new_prices)


def apply_markup_cents(func):
    def wrapper(*args, **kwargs):
        user = args[0]
        result = func(*args, **kwargs)

        price = result[0]
        compare_at = result[1]

        if price:
            price = Decimal(price).quantize(Decimal('.01'), ROUND_HALF_UP)
            cents = safe_int(user.get_config('auto_margin_cents'), None)
            if cents is not None and cents >= 0:
                two_digit_cents = str(cents).zfill(2)
                price = price.to_integral(ROUND_DOWN) + Decimal(f'.{two_digit_cents}')

        if compare_at:
            compare_at = Decimal(compare_at).quantize(Decimal('.01'), ROUND_HALF_UP)
            cents = safe_int(user.get_config('auto_compare_at_cents'), None)
            if cents is not None and cents >= 0:
                two_digit_cents = str(cents).zfill(2)
                compare_at = compare_at.to_integral(ROUND_DOWN) + Decimal(f'.{two_digit_cents}')

        return [price, compare_at]
    return wrapper


@apply_markup_cents
def get_price_markup(user, price, markup_rules):
    compare_at = Decimal('0.00')

    def apply_markup(markup_type, markup, price):
        if markup_type == 'margin_percent':
            return price + price * markup / 100
        elif markup_type == 'margin_amount':
            return price + markup
        elif markup_type == 'fixed_amount':
            return markup

    # Return last created markup rules first
    for markup_rule in markup_rules[::-1]:
        unlimited = markup_rule.max_price < 0
        if markup_rule.min_price <= price < markup_rule.max_price or unlimited:
            markup_value = Decimal(markup_rule.markup_value)
            markup_compare_value = Decimal(markup_rule.markup_compare_value or '0.0')

            if markup_value > 0:
                price = apply_markup(markup_rule.markup_type, markup_value, price)

            if markup_compare_value and markup_compare_value > 0:
                compare_at = apply_markup(markup_rule.markup_type, markup_compare_value, price)

            return [price, compare_at]

    auto_margin = user.get_config('auto_margin', '').rstrip('%') or '0'
    auto_margin = Decimal(auto_margin)
    auto_compare_at = user.get_config('auto_compare_at', '').rstrip('%') or '0'
    auto_compare_at = Decimal(auto_compare_at)
    if auto_margin > 0:
        price = price + price * auto_margin / 100
    if auto_compare_at > 0:
        compare_at = price + price * auto_compare_at / 100

    return [price, compare_at]
