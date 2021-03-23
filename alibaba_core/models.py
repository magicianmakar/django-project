import arrow
import json
import re

from django.contrib.auth.models import User
from django.core.cache import cache
from django.db import models
from django.utils.functional import cached_property

from lib.exceptions import capture_exception
from shopified_core.utils import float_to_str, get_store_api, hash_text, hash_url_filename


class AlibabaAccount(models.Model):
    user = models.ForeignKey(User, related_name='alibaba', on_delete=models.CASCADE)
    access_token = models.TextField(default='')
    expired_at = models.DateTimeField(null=True, blank=True)
    alibaba_user_id = models.CharField(max_length=100, default='', blank=True)
    alibaba_email = models.CharField(max_length=255, default='', blank=True)
    ecology_token = models.TextField(default='')
    ecology_token_expired_at = models.DateTimeField(null=True, blank=True)

    @property
    def request(self):
        from .utils import APIRequest
        return APIRequest(self.access_token)

    def is_expired(self):
        if not self.expired_at:
            return False

        return self.expired_at < arrow.get().datetime

    def is_nearly_expired(self):
        if not self.expired_at:
            return False

        return arrow.get(self.expired_at).is_between(arrow.get().shift(weeks=-3), arrow.get())

    def get_ecology_token(self, refresh=False):
        if not refresh and self.ecology_token_expired_at \
                and self.ecology_token_expired_at < arrow.get().datetime:
            return self.ecology_token

        response = self.request.post('alibaba.dropshipping.token.create')
        token = response['alibaba_dropshipping_token_create_response']['ecology_token']

        self.ecology_token = token
        self.ecology_token_expired_at = arrow.get().shift(days=4).datetime
        self.save()
        return self.ecology_token

    def get_order_ids(self):
        response = self.request.post('alibaba.seller.order.list', params={
            'param_trade_ecology_order_list_query': json.dumps({
                'start_page': 0,
                'role': 'seller',
            })
        })

        order_ids = []
        value = response['alibaba_seller_order_list_response']['result']['value']
        if value:
            for order in value['order_list']['trade_ecology_order']:
                order_ids.append(order['trade_id'])

        return order_ids

    def get_orders(self):
        orders = []
        for order_id in self.get_order_ids():
            response = self.request.post('alibaba.seller.order.get', params={
                'e_trade_id': order_id,
                'language': 'en_Us'
            })

            orders.append(response['alibaba_seller_order_get_response']['value'])

        return orders

    def get_order(self, alibaba_order_id):
        response = self.request.post('alibaba.seller.order.get', params={
            'e_trade_id': alibaba_order_id,
            'language': 'en_Us'
        })
        return response['alibaba_seller_order_get_response']['value']

    def get_logistic_detail(self, alibaba_order_id):
        response = self.request.post('alibaba.seller.order.logistics.get', params={
            'e_trade_id': alibaba_order_id,
            'data_select': 'logistic_order'
        })
        return response['alibaba.seller.order.logistics.get']['value']

    def get_products(self, product_ids, raw=False, use_cache=True):
        from .utils import get_batches

        product_ids = list(set(product_ids))
        api_products = []
        if use_cache:
            for product_id in product_ids:
                product = cache.get(f"alibabaproduct_{product_id}")
                if product:
                    api_products.append(product)

        found_product_ids = [str(p['product_id']) for p in api_products]
        product_ids = [product_id for product_id in product_ids if str(product_id) not in found_product_ids]

        for batch in get_batches(product_ids):
            response = self.request.post('alibaba.dropshipping.product.get', params={
                'param_distribution_sale_product_request': json.dumps({
                    'product_ids': batch,
                })
            })

            if response.get('error'):
                for product_id in batch:
                    api_products.append({'id': product_id, 'error': response['error']})
            else:
                response = response['alibaba_dropshipping_product_get_response']
                products = response.get('value', {}).get('distribution_sale_product', [])
                for product in products:
                    cache.set(f"alibabaproduct_{product['product_id']}", product, timeout=300)
                    api_products.append(product)

        formatted_products = []
        for product in api_products:
            if product.get('error'):
                formatted_products.append(product)
                continue

            images = [product.get('main_image_url')]
            variant_images = {}
            variants_sku = {}
            variants = {}
            variants_info = {}
            variants_map = {}
            for variant in product['product_sku_list']['product_sku']:
                main_variant_image = ''
                image = variant.get('image_url', '')
                if image:
                    main_variant_image = image
                    images.append(image)

                variant_values = []
                variant_skus = []
                for attr in variant.get('sku_name_value_list', {}).get('product_sku_name_value', []):
                    if not variants.get(attr['attr_name_id']):
                        variants[attr['attr_name_id']] = {'title': attr['attr_name_desc'], 'values': []}

                    variants[attr['attr_name_id']]['values'].append(attr['attr_value_desc'])
                    variant_values.append(attr['attr_value_desc'])
                    variant_skus.append(f"{attr['attr_name_id']}:{attr['attr_value_id']}")
                    variants_sku[attr['attr_value_desc']] = f"{attr['attr_name_id']}:{attr['attr_value_id']}"
                    image = attr.get('attr_value_image')
                    if image:
                        main_variant_image = main_variant_image if main_variant_image else image
                        variant_images[hash_url_filename(image)] = attr['attr_value_desc']
                        images.append(image)

                    if not variants_map.get(attr['attr_name_desc']):
                        variants_map[attr['attr_name_desc']] = {'title': attr['attr_name_desc'], 'values': []}
                    map = {
                        'title': attr['attr_value_desc'],
                        'image': image,
                        'sku': f"{attr['attr_name_id']}:{attr['attr_value_id']}",
                    }
                    if map not in variants_map[attr['attr_name_desc']]['values']:
                        variants_map[attr['attr_name_desc']]['values'].append(map)

                variant_name = ' / '.join(variant_values)
                if variant_name:
                    if 'ladder_price_list' in variant:
                        variant_price = variant['ladder_price_list']['ladder_price'][0]['price']['amount']
                    else:
                        variant_price = product['moq_and_price']['moq_unit_price']['amount']
                    variants_info[variant_name] = {
                        'price': float_to_str(variant_price),
                        'compare_at': float_to_str(variant_price),
                        'sku': ';'.join(variant_skus),
                        'image': main_variant_image,
                    }

                if raw and variant_name:
                    variants_info[variant_name]['api'] = variant

            extra_images = []
            for image in re.findall(r'"([\/\/|http]\S+alicdn\S+)"', product.get('description', '')):
                if image.startswith('//'):
                    image = f'https:{image}'
                extra_images.append(image)

            product_price = product['moq_and_price']['moq_unit_price']['amount']

            save_for_later_product = {
                'id': product['product_id'],
                'title': product['name'],
                'price': float_to_str(product_price),
                'compare_at_price': float_to_str(product_price),
                'images': images,
                'type': '',  # TODO: missing field
                'tags': ','.join(product.get('keywords', {}).get('string', '')),
                'vendor': '',
                'description': product.get('description'),
                'original_url': product['detail_url'],
                'store': {
                    'id': product['e_company_id'],
                    'name': 'Alibaba',
                    'url': product['detail_url'],
                },
                'published': False,
                'weight': None,
                'weight_unit': 'g',
                'extra_images': extra_images,
                'variants_images': variant_images,
                'variants_sku': variants_sku,
                'variants': list(variants.values()),
                'variants_info': variants_info,
                'variants_map': list(variants_map.values()),
            }

            if raw:
                save_for_later_product['api'] = product

            formatted_products.append(save_for_later_product)

        return formatted_products

    def get_product(self, product_id):
        return self.get_products([product_id])[0]

    def create_order(self, order_params):
        response = self.request.post('alibaba.buynow.order.create', params={
            'param_order_create_request': json.dumps(order_params)
        })

        if 'error' in response:
            return response

        result = response['alibaba_buynow_order_create_response']
        return result['value']['trade_id']

    def get_shipping_costs(self, product_id, quantity, country_code, zip_code=None):
        cache_key = f"alibabashipment_{product_id}_{quantity}_{country_code}_{zip_code}"
        shippings = cache.get(cache_key)
        if shippings:
            return shippings

        data = {
            'destination_country': country_code,
            'product_id': product_id,
            'quantity': quantity,
        }
        if zip_code:
            data['zip_code'] = zip_code

        response = self.request.post('alibaba.shipping.freight.calculate', {
            'param_freight_template_request': data
        })

        try:
            result = response['alibaba_shipping_freight_calculate_response']
            shippings = result['values']['value']
            shippings = [s for s in shippings if s['shipping_type'] == 'EXPRESS']
            cache.set(cache_key, shippings, timeout=600)
        except KeyError:
            capture_exception(extra={
                'destination_country': country_code,
                'product_id': product_id,
                'quantity': quantity,
                'zip_code': zip_code,
            })
            shippings = []

        return shippings

    def get_order_shipping_costs(self, address, products=[{'e_supplier_id', 'id', 'quantity'}], use_cache=True):
        """ Return all shipping options for selected products

            :param address: dict generated by {store_type}_customer_address function
            :param products: all order products with supplier encrypted id, product source id and quantity
        """
        data = {
            'destination_country': address['country_code'],
            'address': {
                'zip': address['zip'],
                'country': {
                    'code': address['country_code'],
                    'name': address.get('country', ''),
                },
                'address': address.get('address1', ''),
                'province': {
                    'code': address.get('province_code', ''),
                    'name': address.get('province', ''),
                },
                'city': {
                    'code': '',
                    'name': address.get('city', '')
                },
            },
        }

        supplier_products = {}
        for product in products:
            if product['quantity'] == 0:
                continue

            supplier = product['e_supplier_id']
            if supplier not in supplier_products:
                supplier_products[supplier] = []

            supplier_products[supplier].append({
                'product_id': product['id'],
                'quantity': product['quantity'],
            })

        results = {}
        for supplier, products in supplier_products.items():
            data['e_company_id'] = supplier
            data['logistics_product_list'] = products
            shipment_key = hash_text(json.dumps(data, sort_keys=True))

            results[supplier] = []
            if use_cache:
                results[supplier] = cache.get(f"alibaba_order_shipping_{shipment_key}", [])
                if results[supplier]:
                    continue

            response = None
            try:
                response = self.request.post('alibaba.order.freight.calculate', {
                    'param_multi_freight_template_request': data
                })

                if 'error' in response:
                    results[supplier] = response
                    continue

                shippings = []
                for shipping in response['alibaba_order_freight_calculate_response']['value']['logistics_solution']:
                    if shipping.get('shipping_type', '') != 'EXPRESS':
                        continue

                    shipping['fee']['amount'] = float_to_str(shipping['fee']['amount'])
                    shippings.append(shipping)

                cache.set(f"alibaba_order_shipping_{shipment_key}", shippings, timeout=300)
                results[supplier] = shippings
            except:
                capture_exception(extra={
                    'response': response,
                    'results': results,
                })

        return results

    def get_order_payments(self, alibaba_order_id):
        response = self.request.post('alibaba.seller.order.fund.get', {
            'e_trade_id': alibaba_order_id,
        })

        return response['alibaba_seller_order_fund_get_response']['value']

    def allow_message_consumption(self):
        return self.request.post('taobao.tmc.user.permit', {'topics': 'icbu_trade_OrderNotify'})


class AlibabaOrder(models.Model):
    SHOPIFY = 'shopify'
    CHQ = 'chq'
    WOO = 'woo'
    GEAR = 'gear'
    GKART = 'gkart'
    BIGCOMMERCE = 'bigcommerce'
    STORE_TYPES = [
        (SHOPIFY, 'Shopify'),
        (CHQ, 'CommerceHQ'),
        (WOO, 'WooCommerce'),
        (GEAR, 'GearBubble'),
        (GKART, 'GrooveKart'),
        (BIGCOMMERCE, 'BigCommerce')
    ]
    store_type = models.CharField(max_length=15, choices=STORE_TYPES, default=SHOPIFY)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    order_data_ids = models.TextField(blank=True, default='')
    store_id = models.IntegerField()
    store_order_id = models.CharField(max_length=30, blank=True, default='')

    trade_id = models.CharField(max_length=30, blank=True, default='')
    source_status = models.CharField(max_length=50, blank=True, default='unpay')
    currency = models.CharField(max_length=3, default='USD', verbose_name='ISO4217 Currency Code')
    products_cost = models.DecimalField(max_digits=10, decimal_places=2)
    shipping_cost = models.DecimalField(max_digits=10, decimal_places=2)

    created_at = models.DateTimeField(auto_now_add=True)
    delivered_at = models.DateTimeField(null=True)

    def __str__(self):
        return f'<AlibabaOrder: {self.id} - {self.trade_id}>'

    @cached_property
    def alibaba_account(self):
        return self.user.alibaba.first()

    @property
    def status(self):
        return f"ALIBABA_{self.source_status or 'unpay'}"

    @status.setter
    def status(self, new):
        self.source_status = new

    @property
    def payment_details(self):
        return {'cost': {
            'total': float_to_str(self.products_cost + self.shipping_cost),
            'products': float_to_str(self.products_cost),
            'shipping': float_to_str(self.shipping_cost),
            'currency': self.currency or 'USD',
        }}

    def get_api(self):
        return get_store_api(self.store_type)

    def get_mock_request(self):
        class MockRequest:
            META = {}
        return MockRequest()

    def get_fulfilled_items(self, items=None):
        if not items:
            items = self.items.all()

        return {i.order_data_id: {
            'order_track_id': i.order_track_id,
            'products': [i.data_source_id],
            'trade_ids': i.combined_trade_ids or str(self.trade_id)
        } for i in items}

    def handle_tracking(self):
        api = self.get_api()
        request = self.get_mock_request()
        order_data_ids = []

        items = self.items.all()
        for item in items:
            item.save_order_track(api, request)
            item.save()

            if not item.order_track_id:
                raise Exception('Order track not created for Alibaba')

            order_data_ids.append(item.order_data_id)

        self.order_data_ids = ','.join(order_data_ids)
        self.save()
        return self.get_fulfilled_items(items)

    def reload_details(self, order_detail=None):
        if not order_detail:
            order_detail = self.alibaba_account.get_order(self.trade_id)
            order_detail['status'] = order_detail['status_action']['status']
            self.products_cost = float_to_str(order_detail['product_total_amount']['amount'])
            self.shipping_cost = float_to_str(order_detail['shipment_fee']['amount'])
            self.currency = order_detail['total_amount']['currency'] or 'USD'

        self.status = order_detail['status']
        # TODO: Update trackings by product when available in API
        if self.status in ['ALIBABA_delivering', 'ALIBABA_wait_confirm_receipt', 'ALIBABA_trade_success'] \
                and self.items.filter(source_tracking='').exists():
            tracking_details = self.alibaba_account.get_logistic_detail(self.trade_id)
            self.status = tracking_details['logistic_status']
            source_tracking = tracking_details['shipping_order_list']['shippingorderlist'][0]['voucher']['tracking_number']
            self.items.all().update(source_tracking=source_tracking)

        self.save()
        return {
            'details': {
                'status': self.status,
                'orderStatus': self.status,
                'tracking_number': self.source_tracking,
                'source_id': str(self.trade_id),
                'order_details': self.payment_details,
            }
        }


class AlibabaOrderItem(models.Model):
    order = models.ForeignKey(AlibabaOrder, related_name='items', on_delete=models.CASCADE)
    product_id = models.CharField(max_length=30, blank=True, default='')
    variant_id = models.CharField(max_length=30, blank=True, default='')
    quantity = models.IntegerField(default=1)
    unit_cost = models.DecimalField(max_digits=10, decimal_places=2)
    source_tracking = models.CharField(max_length=128, blank=True, default='', db_index=True, verbose_name="Source Tracking Number")

    store_line_id = models.CharField(max_length=30, blank=True, default='')
    is_bundled = models.BooleanField(default=False)
    order_track_id = models.BigIntegerField(null=True, blank=True)
    combined_trade_ids = models.CharField(max_length=512, blank=True, default='')

    @cached_property
    def order_data_id(self):
        return f"{self.order.store_id}_{self.order.store_order_id}_{self.store_line_id}"

    @cached_property
    def data_source_id(self):
        return f"{self.product_id}_{self.variant_id}"

    def save_order_track(self, api, request):
        self.store_api = api
        self.store_api_request = request

        if not self.order_track_id:
            self.create_tracking()

        self.update_tracking()

    def create_tracking(self):
        api_data = {
            'store': self.order.store_id,
            'order_id': self.order.store_order_id,
            'line_id': self.store_line_id,
            'aliexpress_order_id': self.combined_trade_ids or str(self.order.trade_id),
            'source_type': 'alibaba',
        }

        try:
            response = self.store_api.post_order_fulfill(self.store_api_request, self.order.user, api_data)
            result = json.loads(response.content.decode("utf-8"))
            if response.status_code == 200 and result.get('order_track_id'):
                self.order_track_id = result['order_track_id']
            else:
                raise Exception(result)
        except:
            capture_exception()

    def update_tracking(self):
        api_data = {
            'store': self.order.store_id,
            'status': self.order.status,
            'order': self.order_track_id,
            'order_details': json.dumps(self.order.payment_details),
            'tracking_number': self.source_tracking,
            'source_id': self.combined_trade_ids or str(self.order.trade_id),
            'source_type': 'alibaba',
        }
        if self.is_bundled:
            api_data['bundle'] = True

        try:
            response = self.store_api.post_order_fulfill_update(self.store_api_request, self.order.user, api_data)
            if response.status_code != 200:
                result = json.loads(response.content.decode("utf-8"))
                raise Exception(result)
        except:
            capture_exception()