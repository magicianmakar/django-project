import arrow
import json
import re
import requests
import socket
from bs4 import BeautifulSoup
from copy import deepcopy
from decimal import Decimal

from django.conf import settings
from django.contrib.auth.models import User
from django.core.cache import cache
from django.db.models import Q
from django.db.transaction import atomic
from django.shortcuts import get_object_or_404
from django.utils.html import format_html

from leadgalaxy.models import PriceMarkupRule
from leadgalaxy.utils import format_shopify_send_to_store
from lib.aliexpress_api import RestApi, TopException
from lib.exceptions import capture_exception
from metrics.tasks import add_number_metric
from prints.utils import get_price_markup
from shopified_core.models_utils import get_product_model, get_store_model
from shopified_core.utils import dict_val, float_to_str, get_cached_order, get_store_api, safe_int

from .models import AlibabaOrder, AlibabaOrderItem

ALIBABA_DS_SORT_MAP = {
    'most_relevant': 'COMPREHENSIVE_DESC',
    'order_count': 'ORDER_DESC',
}


class TopAuthTokenCreateRequest(RestApi):
    def __init__(self, domain='api.taobao.com', port=443):
        super().__init__(domain, port)
        self.code = None
        self.set_app_info(settings.ALIBABA_APP_KEY, settings.ALIBABA_APP_SECRET)

    def getapiname(self):
        return 'taobao.top.auth.token.create'

    def get_access_token(self, code):
        self.code = code
        try:
            data = self.getResponse(timeout=30)
            token_data = data['top_auth_token_create_response']['token_result']
            return json.loads(token_data)

        except socket.timeout:
            capture_exception()
            return {'error_msg': 'Alibaba is not responding'}

        except TopException as e:
            capture_exception()
            return {
                'error_msg': f'Alibaba: {e.message}',
                'error_code': e.errorcode,
                'sub_code': e.subcode,
            }


class CustomRestApi(RestApi):
    def __init__(self, domain='api.taobao.com', port=443, method='POST', resource=''):
        super().__init__(domain, port)
        self.set_app_info(settings.ALIBABA_APP_KEY, settings.ALIBABA_APP_SECRET)
        self.__apiname = resource
        self.__httpmethod = method

    def getapiname(self):
        return self.__apiname


class APIRequest():
    def __init__(self, access_token=None):
        self.access_token = access_token
        timedelta, timeunit = settings.ALIBABA_API_LIMIT.split('/')
        self.api_call_limit = safe_int(timedelta, 5)
        self.api_refresh_time = timeunit or 'minute'

    def wait_before_request(self):
        cache_timeout = (arrow.get().floor(self.api_refresh_time) - arrow.get()).seconds
        cache_key = f"alibaba_api_call_{arrow.get().floor(self.api_refresh_time).format('YYYYMMDD_HHmmss')}"
        calls_count = cache.get(cache_key, 0)
        cache.set(cache_key, calls_count + 1, timeout=cache_timeout)

        if calls_count > self.api_call_limit:
            seconds = (arrow.get().ceil(self.api_refresh_time) - arrow.get()).seconds
            return {'error': f'Alibaba calls limit reached, {seconds} seconds to reset limits.'}

        return False

    def get_response(self, api, remaining_tries=3):
        wait = self.wait_before_request()
        if wait:
            return wait

        if remaining_tries < 1:
            return {'error': "Alibaba server is unreachable"}

        try:
            return api.getResponse()

        except socket.timeout:
            capture_exception()
            return self.get_response(api, remaining_tries=remaining_tries - 1)

        except ConnectionResetError:
            capture_exception()
            return self.get_response(api, remaining_tries=remaining_tries - 1)

        except Exception as e:
            capture_exception(extra={
                'errorcode': getattr(e, 'errorcode', None),
                'subcode': getattr(e, 'subcode', None),
                'message': getattr(e, 'message', None),
            })

            if e.errorcode == 7 and 'call limited' in e.message.lower():
                seconds = re.findall(r'(\d+).+?(?=seconds)', e.submsg)
                if seconds:
                    return {'error': f'Alibaba calls limit reached, {seconds[0]} seconds to reset limits'}

            if e.errorcode == 15 and e.subcode == 'isp.top-remote-connection-timeout':
                return self.get_response(api, remaining_tries=remaining_tries - 1)

            if e.subcode == 'isv.biz-auth.purchase.invalid':
                return {'error': 'Please re-connect your Alibaba account'}

            # Product prices can change between requests, the first API request will reload cache
            if e.subcode == '430005':
                return {'error': 'A product or shipping cost has changed between requests, please refresh'}

            # User is ordering more than one of the same product with the same variant
            if e.subcode == '4012' and 'repeated' in e.submsg.lower():
                return {'error': 'Ordering repeated products, please review your suppliers'}

            if e.errorcode == 27 and e.subcode == 'invalid-sessionkey':
                return {'error': 'Please re-connect your Alibaba account in Settings'}

            raise AlibabaUnknownError('Unknown error in Alibaba')

    def get(self, resource, params=None):
        return self._request(resource, params, method='GET')

    def post(self, resource, params=None):
        return self._request(resource, params, method='POST')

    def _request(self, resource, params=None, method=''):
        if params is None:
            params = {}

        test_resources = [
            'alibaba.dropshipping.token.create',
            'alibaba.shipping.freight.calculate',
            'alibaba.dropshipping.product.get',
            # 'alibaba.buyer.order.create',
            # 'alibaba.buynow.order.create',
            'alibaba.order.freight.calculate',
            'alibaba.order.logistics.tracking.get',
            'alibaba.dropshipping.order.pay',
            # 'alibaba.seller.order.logistics.get',
            # 'taobao.tmc.user.permit',
        ]

        if resource in test_resources and not settings.ALIBABA_APP_USE_LIVE:
            api = CustomRestApi(resource=resource, domain='pre-gw.api.taobao.com', method=method)
        else:
            api = CustomRestApi(resource=resource, domain='api.taobao.com', method=method)

        api.session = self.access_token
        for key, value in params.items():
            setattr(api, key, value)

        return self.get_response(api)


def get_access_token_url(user):
    """Return Alibaba url that provides the user access token."""
    base_url = 'https://crosstrade.alibaba.com/ecology/service.htm'

    return f"{base_url}?appKey={settings.ALIBABA_APP_KEY}"


def get_alibaba_account(user):
    account = user.alibaba.first()
    if not account:
        default_user = User.objects.get(username=settings.ALIBABA_DEFAULT_USER)
        account = default_user.alibaba.first()

    return account


def get_description_simplified(description):
    soup = BeautifulSoup(description, features='html.parser')
    specs = soup.table

    if not specs:
        return description

    desc = ['<div>']

    for tr in soup.table:
        for row in tr:
            line = [td.get_text() for td in row]
            name = line[0]
            value = ' '.join(line[1:])
            desc.append(f'<b>{name}:</b> {value}<br />')

    desc.append('</div>')

    return '\n'.join(desc)


def apply_user_config(user, product):
    rules = list(PriceMarkupRule.objects.filter(user=user))
    result = get_price_markup(user, Decimal(product['price']), rules)
    product['price'] = str(result[0])
    if result[1] > 0:
        product['compare_at_price'] = str(result[1])

    for variant, info in product['variants_info'].items():
        result = get_price_markup(user, Decimal(info['price']), rules)
        info['price'] = str(result[0])
        if result[1] > 0:
            info['compare_at'] = str(result[1])

    desc_mode = user.get_config('description_mode')
    if desc_mode == 'empty':
        product['description'] = ''
    elif desc_mode == 'custom':
        product['description'] = user.get_config('default_desc', '')
    elif desc_mode == 'simplified':
        try:
            product['description'] = get_description_simplified(product['description'])
        except:
            capture_exception()

    return product


def save_alibaba_products(request, products_data, import_to=None, publish=True):

    ''' Format
    {
        user_id: [
            products,
            list,
        ]
    }
    '''
    result_products = {'saved': [], 'errored': []}
    for user_id, product_ids in products_data.items():
        try:
            user = get_object_or_404(User, id=user_id)
        except:
            capture_exception()
            return

        account = get_alibaba_account(user)

        products = account.get_products(product_ids)
        for api_product in products:
            if 'error' in api_product:
                result_products['errored'].append(api_product['error'])
                continue
            if import_to is None:
                # Default - can be {store_type} or {store_type}_{store_id}
                import_to = user.get_config('alibaba_default_import', 'shopify')
            try:
                store_type, store_id = import_to.split('_')
            except ValueError:
                store_type, store_id = import_to, None

            api_product = apply_user_config(user, api_product)
            original_title = api_product['title']

            if store_id and store_type == 'shopify':
                api_product['title'] = 'Importing...'

            data = {
                'data': json.dumps(api_product),
                'original': json.dumps(api_product),
                'notes': '',
                'activate': len(import_to) == 1,
                'b': True,
            }
            if store_id:
                data['store'] = store_id
            else:
                StoreModel = get_store_model(store_type)
                store = StoreModel.objects.filter(is_active=True, user=user).first()
                if store is not None:
                    data['store'] = store.id

            StoreAPI = get_store_api(store_type)
            if store_type == 'shopify':
                StoreAPI.target = 'save-for-later'
                response = StoreAPI.post_save_for_later(request, user, data)
            else:
                StoreAPI.target = 'product-save'
                response = StoreAPI.post_product_save(request, user, data)

            result = json.loads(response.content.decode("utf-8"))
            product = result['product']

            if store_id and publish:  # Send to Store
                get_product_model(store_type).objects.filter(id=product['id']).update(title='Importing...')

                if store_type == 'shopify':
                    api_product['title'] = original_title
                    data = {
                        'store': store_id,
                        'data': json.dumps(format_shopify_send_to_store(api_product)),
                        'original_url': api_product['original_url'],
                        'product': product['id'],
                        'b': True,
                    }
                    StoreAPI.target = 'shopify'
                    StoreAPI.post_shopify(request, user, data)
                else:
                    # get_product_model(store_type).objects.filter(id=product['id']).update(data=json.dumps(api_product))
                    data = {
                        'product': product['id'],
                        'store': store_id,
                        'publish': 'true' if user.get_config('make_visisble') else 'false',
                    }
                    StoreAPI.target = 'product-export'
                    StoreAPI.post_product_export(request, user, data)
            add_number_metric.apply_async(args=['product', 'alibaba', 1])
        result_products['saved'].append(api_product)
    return result_products


class AlibabaUnknownError(Exception):
    pass


class OrderProcess:
    error_line_ids = []
    error_order_ids = []
    item_products_map = {}

    def __init__(self, user, store, order_data_ids, order_splits={}, selected_shippings={}, verbose=0, use_cache=False):
        self.user = user
        self.store = store
        self.store_type = store.store_type
        self.alibaba_account = user.alibaba.first()
        self.default_shipping = self.alibaba_account.user.models_user.get_config('alibaba_default_shipping', '')
        self.selected_shippings = selected_shippings
        self.orders = self._get_orders(order_data_ids)
        self.order_splits = order_splits
        self.verbose = verbose
        self.use_cache = use_cache

        self.fulfilled_data = {}
        contain_ids = Q()
        for order_data_id in order_data_ids:
            contain_ids |= Q(order_data_ids__icontains=order_data_id)
        for o in AlibabaOrder.objects.prefetch_related('items').filter(contain_ids, store_type=self.store_type, user=self.user):
            items = o.get_fulfilled_items()
            for order_data_id in items:
                if order_data_id in self.fulfilled_data:
                    self.fulfilled_data[order_data_id]['products'] += items[order_data_id]['products']
                else:
                    self.fulfilled_data[order_data_id] = items[order_data_id]

    def _add_product_error(self, order, product, error):
        product['error'] = error
        self.error_line_ids.append([product['item']['id']])
        if product['source_id'] in order['meta']['products']:
            order['meta']['products'][product['source_id']]['quantity'] -= product['quantity']

    def _add_order_error(self, order, error):
        order['error'] = error
        self.error_order_ids.append([order['id']])

    def _has_error(self, order, product=None):
        if product:
            has_product_error = 'error' in product
            has_item_error = product['item']['id'] in self.error_line_ids
            if has_item_error or has_product_error:
                if has_item_error and not has_product_error:
                    self._add_product_error(order, product, 'Fix bundle issues')
                return True

            return False

        if order:
            return order['id'] in self.error_order_ids

    def _get_orders(self, order_data_ids):
        source_ids = set()
        orders = {}
        for order_data_id in set(order_data_ids):
            cached_order_key, cached_order = get_cached_order(self.user, self.store_type, order_data_id)
            if cached_order is None:
                raise AlibabaUnknownError('Orders not found, try refreshing the page')

            if cached_order['is_refunded']:
                continue

            store_id, order_id, line_id = order_data_id.split('_')
            if order_id not in orders:
                orders[order_id] = []

            cached_products = cached_order['products'] if cached_order.get('is_bundle') else [cached_order]
            for cached_product in cached_products:
                source_ids.add(cached_product['source_id'])
            orders[order_id].append([cached_order_key, cached_order])

        self.product_map, self.min_quantity_map = {}, {}
        for product in self.alibaba_account.get_products(source_ids, raw=True, use_cache=self.use_cache):
            self.product_map[product['id']] = product
            min_quantity = product.get('api', {}).get('moq_and_price', {}).get('min_order_quantity')
            self.min_quantity_map[product['id']] = safe_int(min_quantity, 1)

        for cached_orders in orders.values():
            order = None

            for cached_order_key, cached_order in cached_orders:
                order_id = cached_order['order_id']
                if not order:
                    address = cached_order['shipping_address']
                    order = {
                        'id': order_id,
                        'order_key': '_'.join(cached_order_key.split('_')[:-1]),  # Remove line id
                        'order_name': cached_order['order_name'],
                        'notes': cached_order['order']['note'],
                        'phone': cached_order['order']['phone'],
                        'shipping_address': address,
                        'product_total': 0,
                        'products': [],
                        'meta': {'products': {}, 'bundles': {}},
                    }

                product = {
                    'order_data_id': cached_order['id'],
                    'processing_time': 0,
                    'variants': [],
                    'warehouses': [],
                    'variant': {},
                    'is_bundle': cached_order.get('is_bundle', False),
                    'item': {
                        'id': cached_order['line_id'],
                        'title': cached_order['title'],
                        'quantity': safe_int(cached_order['quantity']),
                        'price': float_to_str(cached_order['total']),
                        'total_price': float_to_str(cached_order['total'] * cached_order['quantity']),
                    }
                }

                if product['is_bundle']:
                    cached_products = cached_order['products']
                    order['meta']['bundles'][product['item']['id']] = []
                else:
                    cached_products = [cached_order]

                for cached_product in cached_products:
                    new_product = self.copy_clean_dict(product)
                    new_product['source_id'] = cached_product['source_id']
                    new_product['quantity'] = safe_int(cached_product['quantity'])
                    new_product['shipping_method'] = cached_product['shipping_method']

                    if cached_product['supplier_type'] != 'alibaba':
                        self._add_product_error(order, new_product, 'Product supplier for variant is not Alibaba')
                        order['products'].append(new_product)
                        break

                    # Use sku and title to match variants with accuracy
                    variant_sku, variant_titles = self.get_variant_data(dict_val(cached_product, ['variant', 'variants']))
                    new_product['variant_data'] = {'sku': variant_sku, 'titles': variant_titles}

                    if new_product['source_id'] not in order['meta']['products']:
                        order['meta']['products'][new_product['source_id']] = {
                            'id': new_product['source_id'],
                            'quantity': 0,
                            'e_supplier_id': ''
                        }

                    order['meta']['products'][new_product['source_id']]['quantity'] += new_product['quantity']
                    order['products'].append(new_product)

            yield order

    def get_variant_data(self, variants):
        variant_sku = []
        variant_title = []
        if isinstance(variants, list):
            for variant in variants:
                if not isinstance(variant, dict):
                    variant_title.append(variant)
                else:
                    if 'sku' in variant:
                        variant_sku.append(variant['sku'])

                    if 'title' in variant and variant['title'] != 'Default Title':
                        variant_title.append(variant['title'])
        else:
            return self.get_variant_data([variants])

        return ';'.join(variant_sku), ' / '.join(variant_title)

    def get_step_by_quantity(self, steps, quantity):
        for step in steps:
            max_quantity = step['max_quantity'] if step['max_quantity'] != -1 else quantity
            if step['min_quantity'] <= quantity <= max_quantity:
                return step
        return {}

    def copy_clean_dict(self, copy_dict, default_values=None):
        if default_values is None:
            default_values = []

        new_dict = deepcopy(copy_dict)
        for field, value in default_values:
            new_dict[field] = value
        return new_dict

    def filter_shippings(self, shippings, selected_shipping, similar_codes=None):
        if not shippings:
            return []

        if not similar_codes:
            for options in shippings:
                if not similar_codes:
                    similar_codes = {o['vendor_code'] for o in options}
                similar_codes = similar_codes & {o['vendor_code'] for o in options}

        new_shippings = {}
        for shipping_options in shippings:
            for shipping_option in shipping_options:
                if shipping_option.get('error'):
                    return shipping_option

                vendor_code = shipping_option['vendor_code']
                if vendor_code not in similar_codes:
                    continue

                if not new_shippings.get(vendor_code):
                    shipping_option['fee']['amount'] = Decimal(shipping_option['fee']['amount'])
                    new_shippings[vendor_code] = shipping_option
                else:
                    new_shippings[vendor_code]['fee']['amount'] += Decimal(shipping_option['fee']['amount'])
                new_shippings[vendor_code]['selected'] = selected_shipping == shipping_option['vendor_code']

        return list(new_shippings.values())

    def get_shipping_option(self, order, product=None):
        product_shipping = {}
        if product:
            product_shipping = product.get('shipping_method') or {}

        # Orders can be splitted and also selected shipping
        shipping_key = f"{order['id']}-{order['split']}"

        return self.selected_shippings.get(shipping_key) or product_shipping.get('method') or self.default_shipping

    def is_alibaba_cost_higher(self, product):
        total_paid = product['item'].get('split_price') or product['item']['total_price']
        return Decimal(product.get('variant', {}).get('total_price', 0)) > Decimal(total_paid)

    def get_orders_info(self):
        ready_orders = []

        # Map products and variants from dropified to alibaba
        # Product prices are by quantity and inventory might be out of stock
        for order in self.orders:
            if self._has_error(order):
                continue

            for product in order['products']:
                if self._has_error(order, product):
                    continue

                source_id = product['source_id']
                alibaba_product = self.product_map.get(source_id)
                if alibaba_product is None or alibaba_product.get('error'):
                    product['not_found'] = True
                    error_msg = "Product not found"

                    if isinstance(alibaba_product, dict):
                        error_msg = alibaba_product.get('error')

                    self._add_product_error(order, product, error_msg)
                    continue

                if not alibaba_product['api']['is_can_place_order']:
                    self._add_product_error(order, product, "Not a dropshipping product")

                product['title'] = alibaba_product['api']['name']
                # Calculate shipping grouping by supplier to get better discounts
                product['e_supplier_id'] = alibaba_product['api']['e_company_id']
                order['meta']['products'][source_id]['e_supplier_id'] = product['e_supplier_id']

                order_quantity = order['meta']['products'][source_id]['quantity']
                if order_quantity < self.min_quantity_map[source_id]:
                    self._add_product_error(order, product, f'Minimum product quantity needed: {self.min_quantity_map[source_id]}')

                ladder = alibaba_product['api'].get('ladder_period_list', {}).get('ladder_period', [])
                step = self.get_step_by_quantity(ladder, order_quantity)
                product['processing_time'] = step.get('process_period', 0)

                # Both variants sku and title are located under variants_info dict
                for variant_names, variant in alibaba_product['variants_info'].items():
                    clean_variant = self.copy_clean_dict(variant, [('price', None), ('name', variant_names)])
                    if variant['sku'] in product['variant_data']['sku']:
                        clean_variant['selected'] = True

                    for variant_name in variant_names.split(' / '):
                        if variant_name not in product['variant_data']['titles']:
                            break
                    else:
                        clean_variant['selected'] = True

                    # Price can be unique or by quantity according to a price ladder
                    ladder = variant['api']['ladder_price_list']['ladder_price']
                    step = self.get_step_by_quantity(ladder, order_quantity)
                    clean_variant['price'] = float_to_str(step.get('price', {}).get('amount', 0))

                    if self.verbose > 0:
                        variant['name'] = variant_names
                        product['variants'].append(variant)

                    if clean_variant.get('selected'):
                        clean_variant['id'] = variant['api']['sku_id']
                        clean_variant['title'] = variant_names
                        clean_variant['total_price'] = float_to_str(Decimal(clean_variant['price']) * product['quantity'])
                        product['variant'] = clean_variant

                        if self.verbose == 0:
                            break

                # Single variant products need a default variant for ordering
                if not product['variant'] and not alibaba_product['variants_info'] \
                        and not dict_val(product['variant_data'], ['sku', 'title']):
                    variant = alibaba_product['api']['product_sku_list']['product_sku'][0]
                    ladder = variant['ladder_price_list']['ladder_price']
                    step = self.get_step_by_quantity(ladder, order_quantity)
                    price = step.get('price', {}).get('amount', 0)
                    product['variant'] = {
                        'api': variant,
                        'id': '',  # Used as blank in template and products map
                        'title': 'Default',
                        'price': float_to_str(price),
                        'total_price': float_to_str(Decimal(price) * product['quantity']),
                        'selected': True
                    }

                if product['variant']:
                    if product['item']['id'] in order['meta']['bundles']:
                        order['meta']['bundles'][product['item']['id']].append(Decimal(product['variant']['total_price']))

                    # TODO: Inventory check must match warehouse 'dispatch_country' with shipping 'dispatch_country'
                    warehouses = product['variant']['api'].get('inventory_list', {}).get('inventory', [])
                    if warehouses:
                        for warehouse in warehouses:
                            if product['quantity'] < warehouse['inventory']:
                                if self.verbose > 0:
                                    product['warehouses'].append(warehouse)
                                break
                        else:
                            self._add_product_error(order, product, 'Out of stock')
                else:
                    self._add_product_error(order, product, 'Variant not found')

                # Prevent placing bundles with wrong alibaba trade id as OrderTrack.source_id
                order_data_id = product['order_data_id']
                data_source_id = f"{product['source_id']}_{product.get('variant', {}).get('id')}"
                if data_source_id in self.fulfilled_data.get(order_data_id, {}).get('products', []):
                    trade_ids = self.fulfilled_data.get(order_data_id, {}).get('trade_ids')
                    self._add_product_error(order, product, f"Item already placed: {', '.join(trade_ids.split(','))}")

                self.item_products_map.setdefault(order_data_id, {})
                self.item_products_map[order_data_id][data_source_id] = product

            for product in order['products']:
                if product.get('not_found'):
                    continue

                # Bundled items have multiple products
                # Price for bundles should be split to show profits per sourced product
                if product['item']['id'] in order['meta']['bundles']:
                    total_sourced_cost = sum(order['meta']['bundles'][product['item']['id']])
                    total_original_price = Decimal(product['item']['total_price'])
                    sourced_cost = Decimal(product.get('variant', {}).get('total_price', 0))
                    split_price = total_original_price * (Decimal(sourced_cost) / total_sourced_cost)
                    product['item']['split_price'] = float_to_str(split_price)

                product['cost_more'] = self.is_alibaba_cost_higher(product)

            order['success'] = 'Ready'
            if self.order_splits:
                ready_orders += self.separate_order_by_mapping(order)
            else:
                ready_orders += self.separate_order_by_supplier(order)

        return ready_orders

    def separate_order_by_mapping(self, order):
        new_orders = []
        order_id = str(order['id'])
        bundled_items = {}
        for split_id in self.order_splits[order_id]:
            clean_order = self.copy_clean_dict(order, [('split', split_id), ('products', []), ('shippings', []),
                                                       ('shipping_options', {})])
            clean_order['meta']['products'] = {}

            for order_data_id in self.order_splits[order_id][split_id]:
                for data_source_id in self.order_splits[order_id][split_id][order_data_id]:
                    product = self.item_products_map.get(order_data_id, {}).get(data_source_id)
                    if not product:
                        continue

                    clean_order['products'].append(product)
                    if product.get('not_found'):
                        continue

                    if product['is_bundle']:
                        bundled_items.setdefault(order_data_id, [])
                        bundled_items[order_data_id].append(data_source_id)

                    if product['source_id'] not in clean_order['meta']['products']:
                        clean_order['meta']['products'][product['source_id']] = {
                            'id': product['source_id'],
                            'quantity': 0,
                            'e_supplier_id': product['e_supplier_id']
                        }

                    clean_order['meta']['products'][product['source_id']]['quantity'] += product['quantity']

                shippings = self.alibaba_account.get_order_shipping_costs(
                    clean_order['shipping_address'],
                    list(clean_order['meta']['products'].values()),
                    use_cache=self.use_cache
                )
                selected_shipping = self.get_shipping_option(clean_order)
                filtered_shippings = self.filter_shippings(list(shippings.values()), selected_shipping)
                if 'error' in filtered_shippings:
                    self._add_order_error(clean_order, filtered_shippings['error'])
                    continue

                clean_order['shippings'] = filtered_shippings

                if self.verbose > 0:
                    clean_order['shipping_options'] = shippings

            new_orders.append(clean_order)

        for order_data_id, data_source_ids in bundled_items.items():
            if len(data_source_ids) != len(self.item_products_map[order_data_id]):
                for source_id, product in self.item_products_map[order_data_id].items():
                    self._add_product_error(order, product, "Can't split bundled products")

        return new_orders

    def separate_order_by_supplier(self, order):
        error_products = []
        shipping_map = self.alibaba_account.get_order_shipping_costs(
            order['shipping_address'],
            list(order['meta']['products'].values()),
            use_cache=self.use_cache
        )

        # Orders must have a single shipping method but items have multiple, split if necessary
        clean_order = self.copy_clean_dict(order, [('split', 0), ('products', []), ('shippings', []),
                                                   ('shipping_options', {})])
        new_orders = [clean_order]

        for product in order['products']:
            if self._has_error(order, product):
                error_products.append(product)
                continue

            # Order items must have at least one similar shipping option
            source_shippings = shipping_map.get(product['e_supplier_id'], [])
            if not source_shippings:
                self._add_product_error(order, product, 'Shipping options not found, check the shipping address')

            if 'error' in source_shippings:
                self._add_product_error(order, product, source_shippings['error'])
                continue

            for i, new_order in enumerate(new_orders):
                selected_shipping = self.get_shipping_option(new_order, product)

                if not new_order['shippings']:
                    # Initialize first item shipment
                    new_order['products'].append(product)
                    new_order['shippings'] = source_shippings
                    for shipping_option in new_order['shippings']:
                        shipping_option['selected'] = selected_shipping == shipping_option['vendor_code']

                    if self.verbose > 0:
                        new_order['shipping_options'][product['e_supplier_id']] = source_shippings

                elif product['e_supplier_id'] in [p['e_supplier_id'] for p in new_order['products']]:
                    # Shippings are by supplier, when found existing, just add product and item to order
                    new_order['products'].append(product)

                elif i == len(new_orders) - 1:  # Make sure its the end of iteration or it will split all orders
                    # Add product to a new copied order
                    clean_order = self.copy_clean_dict(order, [('split', i + 1), ('products', []), ('shippings', []),
                                                               ('shipping_options', {})])
                    new_orders.append(clean_order)

                else:
                    continue
                    # No need to reduce shippings to only similars if there is none
                    new_codes = [s['vendor_code'] for s in source_shippings]
                    lowest, lowest_vendor = None, None
                    for shipping in source_shippings:
                        cost = Decimal(shipping['fee']['amount'])
                        if lowest is None or cost < lowest:
                            lowest = cost
                            lowest_vendor = shipping['vendor_code']

                    existing_codes = [s['vendor_code'] for s in new_order['shippings']]
                    similar_codes = set(new_codes) & set(existing_codes)
                    if len(similar_codes) > 0 and lowest_vendor in similar_codes:  # Add to same order
                        new_order['products'].append(product)

                        # Reduce all order shippings to item's similar shippings
                        new_order['shippings'] = self.filter_shippings(
                            [new_order['shippings'], source_shippings],
                            selected_shipping,
                            similar_codes
                        )

                        if self.verbose > 0:
                            new_order['shipping_options'][product['e_suzpplier_id']] = source_shippings

                    elif i == len(new_orders) - 1:  # Make sure its the end of iteration or it will split all orders
                        # Add product to a new copied order
                        clean_order = self.copy_clean_dict(order, [('split', i + 1), ('products', []), ('shippings', []),
                                                                   ('shipping_options', {})])
                        new_orders.append(clean_order)

        if error_products:
            if new_orders[0]['products']:
                clean_order = self.copy_clean_dict(order, [('split', len(new_orders)), ('products', []),
                                                           ('shippings', []), ('shipping_options', {})])
                clean_order['products'] = error_products
                new_orders.append(clean_order)
            else:
                clean_order = new_orders[0]
                clean_order['products'] = error_products

        return new_orders

    def create_unpaid_orders(self, orders):
        combined_trade_ids = {}
        trades = []
        for order in orders:
            if self._has_error(order):
                continue

            processing_times = [1]
            product_list = []
            order['product_total'] = Decimal('0.00')
            for product in order['products']:
                if self._has_error(order, product):
                    continue

                # Always select longest processing time for the order
                processing_times.append(safe_int(product['processing_time']))
                order['product_total'] += Decimal(product['variant']['total_price'])

                product_list.append({
                    'product_id': product['source_id'],
                    'sku_id': product['variant']['id'] or None,
                    'quantity': product['quantity'],
                    'unit_price_str': product['variant']['price'],
                })

            if not product_list:
                continue

            shipping = next(filter(lambda s: s.get('selected'), order['shippings']), None)
            if shipping is None:
                self._add_order_error(order, 'Shipping option not selected')
                continue

            address = order['shipping_address']
            param_order_create = {
                'logistics_detail': {
                    'shipment_address': {
                        'zip': address['zip'],
                        'country': address['country'],
                        'country_code': address['country_code'],
                        'address': address['address1'],
                        'alternate_address': address['address2'],
                        'city': address['city'],
                        'province': dict_val(address, ['province', 'province_code']),
                        'contact_person': f"{address.get('first_name', '')} {address.get('last_name', '')}",
                        'telephone': {
                            'country': order['phone']['country'],
                            'number': order['phone']['number'],
                            'area': order['phone']['code'],
                        },
                    },
                    'shipment_date': {
                        'type': 'relative',
                        'duration': max(processing_times)
                    },
                    'carrier_code': shipping['vendor_code'],
                },
                'payment_detail': {
                    'shipment_fee': float_to_str(shipping['fee']['amount']),
                    'total_amount': float_to_str(order['product_total'] + Decimal(shipping['fee']['amount'])),
                },
                'remark': order['notes'],
                'biz_code': settings.ALIBABA_APP_KEY,
                'channel_refer_id': order['id'],
                'properties': {
                    'platform': {
                        'chq': 'CommerceHQ',
                        'woo': 'WooCommerce',
                        'gkart': 'GrooveKart',
                        'bigcommerce': 'BigCommerce',
                    }.get(self.store_type, 'Shopify'),
                    'orderId': order['id']
                },
                'product_list': product_list,
            }

            order['success'] = 'Order Placed'

            try:
                trade_id = self.alibaba_account.create_order(param_order_create)
            except:
                capture_exception()
                raise AlibabaUnknownError('Failed to place orders, please contact support')

            if not trade_id:
                raise AlibabaUnknownError('Failed to place orders, try again or contact support')
            elif isinstance(trade_id, dict) and 'error' in trade_id:
                raise AlibabaUnknownError(trade_id['error'])

            trade = {'trade_id': trade_id, 'order_id': order['id'], 'items': [], 'defaults': {
                'shipping_cost': Decimal(param_order_create['payment_detail']['shipment_fee']),
                'products_cost': Decimal(float_to_str(order['product_total'])),
                'currency': 'USD',
            }}

            # Collect ordered items with trade ids so we can save item track id properly
            for product in order['products']:
                if self._has_error(order, product):
                    continue

                trade['items'].append({
                    'order_data_id': product['order_data_id'],

                    'product_id': product['source_id'],
                    'variant_id': product['variant']['id'],
                    'quantity': product['quantity'],
                    'unit_cost': product['variant']['price'],
                    'source_tracking': '',

                    'store_line_id': product['item']['id'],
                    'is_bundled': product['is_bundle'],
                    'order_track_id': None,
                    'combined_trade_ids': '',
                })

                combined_trade_ids.setdefault(product['order_data_id'], [])
                combined_trade_ids[product['order_data_id']].append(str(trade['trade_id']))

            trades.append(trade)

        alibaba_order_ids = []
        with atomic():
            for trade in trades:
                order, created = AlibabaOrder.objects.get_or_create(
                    store_type=self.store_type,
                    store_id=self.store.id,
                    store_order_id=trade['order_id'],
                    trade_id=trade['trade_id'],
                    user=self.user,
                    defaults=trade['defaults']
                )
                if not created:
                    raise AlibabaUnknownError('Found Alibaba attempt to duplicate placed order')

                for item in trade['items']:
                    order_data_id = item['order_data_id']
                    trade_ids = combined_trade_ids[order_data_id]
                    if len(trade_ids) > 1:  # Bundled tracking creation
                        item['combined_trade_ids'] = ','.join(trade_ids)

                    if self.fulfilled_data.get(order_data_id):
                        item['order_track_id'] = self.fulfilled_data[order_data_id]['order_track_id']

                    del item['order_data_id']
                    AlibabaOrderItem.objects.create(
                        order=order,
                        **item
                    )

                self.fulfilled_data.update(order.handle_tracking())
                alibaba_order_ids.append(order.id)

        return orders, alibaba_order_ids


def get_batches(items, batch_size=10):
    batch = []

    for item in items:
        batch.append(item)
        if len(batch) == batch_size:
            yield batch

    if batch:
        yield batch


def alibaba_shipping_info(alibaba_account, product_id, country_code):
    cache_key = f"alibaba_shipping_info_{product_id}_{country_code}"
    freight_data = cache.get(cache_key)
    if freight_data is not None:
        return freight_data

    shippings = alibaba_account.get_shipping_costs(product_id, 1, country_code)

    freight_data = {
        'freight': []
    }
    for i in shippings:
        freight_data['freight'].append({
            'price': i['fee']['amount'],
            'companyDisplayName': i['vendor_name'],
            'company': i['vendor_code'],
            'time': i['delivery_time'],
            'isTracked': True,  # TODO: Get value from response
        })

    cache.set(cache_key, freight_data, timeout=43200)

    return freight_data


def get_tracking_links(trade_ids, default_url=None):
    result = []

    for trade_id in trade_ids:
        order = AlibabaOrder.objects.get(trade_id=trade_id)
        item = order.items.first()
        if not item:
            continue

        if not item.source_tracking:
            continue

        tracking_url = order.tracking_url
        if not tracking_url:
            if not default_url:
                continue
            tracking_url = default_url.format(item.source_tracking)

        result.append([item.source_tracking, tracking_url])

    if not result:
        return ''
    elif len(result) == 1:
        return result[0][1]
    else:
        return result


def get_search(url, **kwargs):
    headers = {'Content-type': 'application/json;charset=UTF-8'}

    price_min = kwargs['price_min']
    price_max = kwargs['price_max']
    category = kwargs.get('category', '')
    data = {
        "keyword": kwargs['search_query'],
        "currency": kwargs['currency'],
        "sortType": ALIBABA_DS_SORT_MAP.get(kwargs['sort'], 'COMPREHENSIVE_DESC'),
        "pageNo": kwargs['page'],
        "pageSize": 20,
    }
    if price_min:
        data['priceFrom'] = price_min
    if price_max:
        data['priceTo'] = price_max
    if category:
        data['category'] = str(category)

    response = requests.post(url, headers=headers, data=json.dumps(data))

    api_products = response.json()['data'].get('list', [])
    total_results = response.json()['data']['page']['totalNum']
    results = []

    for product in api_products:
        results.append({
            'alibaba_product_id': product['productId'],
            'title': format_html(product['subject']),
            'price_range': product['dsPrice'],
            'shipping_time': product['shippingTime'],
            'url': product['detail'].split('?')[0],
            'image': product['image'],
            'shipping_price': product['freight'],
            'moq': product['moq'],
        })

    products = {'count': total_results, 'results': results}

    return products
