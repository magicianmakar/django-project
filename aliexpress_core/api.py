
import requests
from collections import defaultdict

from django.core.cache import cache
from django.http import HttpResponse, JsonResponse

from aliexpress_core.models import AliexpressAccount
from aliexpress_core.settings import API_KEY, API_SECRET
from aliexpress_core.utils import FindProductViaApi, MaillingAddress, PlaceOrder, PlaceOrderRequest, ProductBaseItem
from bigcommerce_core.models import BigCommerceOrderTrack, BigCommerceProduct, BigCommerceStore
from bigcommerce_core.utils import get_bigcommerce_order_data, get_order_product_data
from commercehq_core.models import CommerceHQOrderTrack, CommerceHQProduct, CommerceHQStore
from commercehq_core.utils import get_chq_order
from leadgalaxy.models import ShopifyOrderTrack, ShopifyProduct, ShopifyStore
from leadgalaxy.utils import get_shopify_order
from groovekart_core.models import GrooveKartOrderTrack, GrooveKartProduct, GrooveKartStore
from groovekart_core.utils import get_gkart_order
from lib.exceptions import capture_exception
from shopified_core import permissions
from shopified_core.exceptions import AliexpressFulfillException
from shopified_core.mixins import ApiResponseMixin
from shopified_core.utils import app_link
from woocommerce_core.models import WooOrderTrack, WooProduct, WooStore
from woocommerce_core.utils import get_woo_order

from .utils import save_aliexpress_products


class AliexpressFulfillHelper():
    def __init__(self, store, order_id, items, shipping_address, order_notes):
        self.store = store
        self.order_id = order_id
        self.items = items
        self.shipping_address = shipping_address
        self.order_notes = order_notes
        self.order_success_msg = ''

        self.reset_errors()

    def reset_errors(self):
        self.order_errors = []
        self.order_item_errors = defaultdict(list)

    def order_error(self, err):
        self.order_errors.append(err)
        raise AliexpressFulfillException(err)

    def order_item_error(self, line_id, err):
        self.order_item_errors[str(line_id)].append(err)

    def has_errors(self):
        return self.order_errors or self.order_item_errors

    def errors(self):
        return {
            'errors': {
                'order': self.order_errors,
                'items': self.order_item_errors,
            }
        }

    def ds_product_data(self, product_id, aliexpress_account):
        cache_key = f"aliexpress_drop_ship_product_details_{product_id}"
        aliexpress_product_result = cache.get(cache_key, {})
        product_data = AliexpressProduct(product_id, aliexpress_account)
        if not aliexpress_product_result:
            aliexpress_product_result = product_data.get_product_data()
            if aliexpress_product_result is None:
                return None
            else:
                cache.set(cache_key, aliexpress_product_result, timeout=300)
        sku_data = product_data.get_product_sku_data(aliexpress_product_result)
        return sku_data

    def find_ds_product_sku(self, product_dict, aliexpress_account):
        sku_attr = ''
        variant_mapping_error_count = 0
        temp_variants = product_dict.get('variants') or product_dict.get('variant')

        try:
            if len(temp_variants) == 1:
                if isinstance(temp_variants[0], dict):
                    if temp_variants[0]['title'] == 'Default Title':
                        sku_attr = ''
                    else:
                        sku_attr = ';'.join([f"{v['sku']}#{v['title'] or ''}".strip('#') for v in temp_variants])
                elif temp_variants[0] == 'Default Title':
                    sku_attr = ''
            elif len(temp_variants) == 0:
                sku_attr = ''
            else:
                sku_attr = ';'.join([f"{v['sku']}#{v['title'] or ''}".strip('#') for v in temp_variants])
        except:
            aliexpress_variant_sku_dict = self.ds_product_data(product_dict['source_id'], aliexpress_account)
            if aliexpress_variant_sku_dict is None:
                return None

            try:
                product_variant_title_list = [v['title'] for v in temp_variants]
            except:
                variant_title_list = map(lambda title: title.strip(), temp_variants)  # if item variant list contain spaces
                product_variant_title_list = list(variant_title_list)

            product_variant_title_list = sorted(product_variant_title_list)
            product_variant_title = '/'.join(product_variant_title_list)
            if product_variant_title in aliexpress_variant_sku_dict:
                sku_attr = aliexpress_variant_sku_dict[product_variant_title]
            elif variant_mapping_error_count == 0:
                return None
        return sku_attr

    def set_order_success_msg(self, msg):
        self.order_success_msg = msg

    def fulfill_woo_order(self):
        self.order = get_woo_order(self.store, self.order_id)
        order_tracks = {}
        for i in WooOrderTrack.objects.filter(store=self.store, order_id=self.order['id']).defer('data'):
            order_tracks[f'{i.order_id}-{i.line_id}'] = i

        need_fulfill_items = {}
        for el in self.order['line_items']:
            if str(el['id']) not in self.items:
                continue
            item = self.items[str(el['id'])]
            variant_id = el['variation_id']
            if not el['product_id']:
                if variant_id:
                    product = WooProduct.objects.filter(store=self.store, title=el['title'], source_id__gt=0).first()
                else:
                    product = None
            else:
                product = WooProduct.objects.filter(store=self.store, source_id=el['product_id']).first()
            woo_order = order_tracks.get(f"{self.order['id']}-{el['id']}")
            if not product or woo_order:
                continue
            variant_id = product.get_real_variant_id(variant_id)
            supplier = product.get_supplier_for_variant(variant_id)

            if product.have_supplier() and supplier and supplier.is_aliexpress:
                item.update({
                    'line': el,
                    'supplier': supplier,
                    'product': product
                })

                need_fulfill_items[str(el['id'])] = item

        if not need_fulfill_items:
            return self.set_order_success_msg('Order have no items that need ordering')

        self.items = need_fulfill_items
        self.fulfill_aliexpress_order('woo')

    def fulfill_chq_order(self):
        self.order = get_chq_order(self.store, self.order_id)
        order_tracks = {}
        for i in CommerceHQOrderTrack.objects.filter(store=self.store, order_id=self.order['id']).defer('data'):
            order_tracks[f'{i.order_id}-{i.line_id}'] = i

        need_fulfill_items = {}
        for el in self.order['items']:
            if str(el['data']['id']) not in self.items:
                continue
            item = self.items[str(el['data']['id'])]
            variant_id = el['data']['variant']['id']
            if not el['data']['product_id']:
                if variant_id:
                    product = CommerceHQProduct.objects.filter(store=self.store, title=el['data']['title'], source_id__gt=0).first()
                else:
                    product = None
            else:
                product = CommerceHQProduct.objects.filter(store=self.store, source_id=el['data']['product_id']).first()
            chq_order = order_tracks.get(f"{self.order['id']}-{el['data']['id']}")
            if not product or chq_order:
                continue
            variant_id = product.get_real_variant_id(variant_id)
            supplier = product.get_supplier_for_variant(variant_id)

            if product.have_supplier() and supplier and supplier.is_aliexpress:
                item.update({
                    'line': el,
                    'supplier': supplier,
                    'product': product
                })

                need_fulfill_items[str(el['data']['id'])] = item

        if not need_fulfill_items:
            return self.set_order_success_msg('Order have no items that need ordering')

        self.items = need_fulfill_items
        self.fulfill_aliexpress_order('chq')

    def fulfill_bigcommerce_order(self):
        self.order = get_bigcommerce_order_data(self.store, self.order_id)
        self.order_items = get_order_product_data(self.store, self.order)
        order_tracks = {}
        for i in BigCommerceOrderTrack.objects.filter(store=self.store, order_id=self.order['id']).defer('data'):
            order_tracks[f'{i.order_id}-{i.line_id}'] = i

        need_fulfill_items = {}
        for el in self.order_items:
            if str(el['id']) not in self.items:
                continue
            item = self.items[str(el['id'])]
            variant_id = el['variant_id']
            if not el['product_id']:
                if variant_id:
                    product = BigCommerceProduct.objects.filter(store=self.store, title=el['name'], source_id__gt=0).first()
                else:
                    product = None
            else:
                product = BigCommerceProduct.objects.filter(store=self.store, source_id=el['product_id']).first()
            bigcommerce_order = order_tracks.get(f"{el['order_id']}-{el['id']}")
            if not product or bigcommerce_order:
                continue
            variant_id = product.get_real_variant_id(variant_id)
            supplier = product.get_supplier_for_variant(variant_id)

            if product.have_supplier() and supplier and supplier.is_aliexpress:
                item.update({
                    'line': el,
                    'supplier': supplier,
                    'product': product
                })

                need_fulfill_items[str(el['id'])] = item

        if not need_fulfill_items:
            return self.set_order_success_msg('Order have no items that need ordering')

        self.items = need_fulfill_items
        self.fulfill_aliexpress_order('bigcommerce')

    def fulfill_gkart_order(self):
        self.order = get_gkart_order(self.store, self.order_id)
        order_tracks = {}
        for i in GrooveKartOrderTrack.objects.filter(store=self.store, order_id=self.order['id']).defer('data'):
            order_tracks[f'{i.order_id}-{i.line_id}'] = i

        need_fulfill_items = {}
        for el in self.order['line_items']:
            if str(el['id']) not in self.items:
                continue

            item = self.items[str(el['id'])]
            variant_id = el['variants']['variant_id']
            if not el['product_id']:
                if variant_id:
                    product = GrooveKartProduct.objects.filter(store=self.store, title=el['title'], source_id__gt=0).first()
                else:
                    product = None
            else:
                product = GrooveKartProduct.objects.filter(store=self.store, source_id=el['product_id']).first()

            gkart_order = order_tracks.get(f"{self.order['id']}-{el['id']}")

            if not product or gkart_order:
                continue

            variant_id = product.get_real_variant_id(variant_id)
            supplier = product.get_supplier_for_variant(variant_id)
            if product.have_supplier() and supplier and supplier.is_aliexpress:
                item.update({
                    'line': el,
                    'supplier': supplier,
                    'product': product
                })

                need_fulfill_items[str(el['id'])] = item

        if not need_fulfill_items:
            return self.set_order_success_msg('Order have no items that need ordering')

        self.items = need_fulfill_items

        self.fulfill_aliexpress_order('gkart')

    def fulfill_shopify_order(self):
        self.order = get_shopify_order(self.store, self.order_id)

        order_tracks = {}
        for i in ShopifyOrderTrack.objects.filter(store=self.store, order_id=self.order['id']).defer('data'):
            order_tracks[f'{i.order_id}-{i.line_id}'] = i

        need_fulfill_items = {}
        for el in self.order['line_items']:
            if str(el['id']) not in self.items:
                continue

            item = self.items[str(el['id'])]
            variant_id = el['variant_id']
            if not el['product_id']:
                if variant_id:
                    product = ShopifyProduct.objects.filter(store=self.store, title=el['title'], shopify_id__gt=0).first()
                else:
                    product = None
            else:
                product = ShopifyProduct.objects.filter(store=self.store, shopify_id=el['product_id']).first()

            shopify_order = order_tracks.get(f"{self.order['id']}-{el['id']}")

            if not product or shopify_order or el['fulfillment_status'] == 'fulfilled' or (product and product.is_excluded):
                continue

            variant_id = product.get_real_variant_id(variant_id)
            supplier = product.get_supplier_for_variant(variant_id)
            if product.have_supplier() and supplier and supplier.is_aliexpress:
                item.update({
                    'line': el,
                    'supplier': supplier,
                    'product': product
                })

                need_fulfill_items[str(el['id'])] = item

        if not need_fulfill_items:
            return self.set_order_success_msg('Order have no items that need ordering')

        self.items = need_fulfill_items

        self.fulfill_aliexpress_order('shopify')

    def fulfill_aliexpress_order(self, store_type):
        order_fulfill_url = app_link('api/order-fulfill')
        if store_type == 'woo':
            order_fulfill_url = app_link('api/woo/order-fulfill')
        elif store_type == 'chq':
            order_fulfill_url = app_link('api/chq/order-fulfill')
        elif store_type == 'bigcommerce':
            order_fulfill_url = app_link('api/bigcommerce/order-fulfill')
        elif store_type == 'gkart':
            order_fulfill_url = app_link('api/gkart/order-fulfill')

        aliexpress_order = PlaceOrder()
        aliexpress_order.set_app_info(API_KEY, API_SECRET)

        address = MaillingAddress()
        address.contact_person = self.shipping_address['name']
        address.full_name = self.shipping_address['name']
        address.address = self.shipping_address['address1']
        address.address2 = self.shipping_address['address2']
        address.city = self.shipping_address['city']
        address.province = self.shipping_address['province']
        address.zip = self.shipping_address['zip']
        address.country = self.shipping_address['country_code']

        try:
            address.phone_country, address.mobile_no = self.shipping_address['phone'].split('-')
        except:
            return self.order_error("Invalid Phone number. Please reenter the number with dialing code separated by a '-'.eg: +1-987654321")

        req = PlaceOrderRequest()
        req.setAddress(address)

        aliexpress_account = AliexpressAccount.objects.filter(user=self.store.user).first()
        if not aliexpress_account:
            return self.order_error("No AliExpress account found")

        aliexpress_variant_sku_dict = ''

        for line_id, line_item in self.items.items():
            aliexpress_variant_sku_dict = ''
            req.product_items = []
            if line_item['is_bundle']:
                for i in line_item['products']:
                    item = ProductBaseItem()
                    item.product_count = i['quantity']
                    item.product_id = i['source_id']
                    sku_attr = self.find_ds_product_sku(i, aliexpress_account)
                    if sku_attr is not None:
                        item.sku_attr = sku_attr
                    else:
                        return self.order_error('Variant mapping is not set')

                    if i.get('shipping_method') is not None:
                        item.logistics_service_name = i['shipping_method']['method']
                    item.order_memo = self.order_notes
                    req.add_item(item)
            else:
                item = ProductBaseItem()
                item.product_count = line_item['quantity']
                item.product_id = line_item['source_id']

                product_obj = line_item['product']
                country_code = self.shipping_address['country_code']

                if store_type == 'chq':
                    variant_id = line_item['line']['data']['variant']['id']
                elif store_type == 'woo':
                    variant_id = line_item['line']['variation_id']
                elif store_type == 'gkart':
                    variant_id = line_item['line']['variants']['variant_id']
                else:
                    variant_id = line_item['line']['variant_id']

                shipping_mapping = product_obj.get_shipping_for_variant(line_item['supplier'].id, variant_id, country_code)
                if shipping_mapping is not None:
                    item.logistics_service_name = shipping_mapping.get('method')

                try:
                    if len(line_item['variant']) == 1:
                        if line_item['variant'][0]['title'] == 'Default Title':
                            item.sku_attr = ''
                        else:
                            item.sku_attr = ';'.join([f"{v['sku']}#{v['title'] or ''}".strip('#') for v in line_item['variant']])
                    elif len(line_item['variant']) == 0:
                        item.sku_attr = ''
                    else:
                        item.sku_attr = ';'.join([f"{v['sku']}#{v['title'] or ''}".strip('#') for v in line_item['variant']])
                except:
                    aliexpress_variant_sku_dict = self.ds_product_data(line_item['source_id'], aliexpress_account)
                    if aliexpress_variant_sku_dict is None:
                        self.order_item_error(line_id, 'This item is discontinued in Aliexpress.')
                        continue

                    try:
                        product_variant_title_list = [v['title'] for v in line_item['variant']]
                    except:
                        variant_title_list = map(lambda title: title.strip(), line_item['variant'])  # if item variant list contain spaces
                        product_variant_title_list = list(variant_title_list)

                    product_variant_title_list = sorted(product_variant_title_list)
                    product_variant_title = '/'.join(product_variant_title_list)
                    if product_variant_title in aliexpress_variant_sku_dict:
                        item.sku_attr = aliexpress_variant_sku_dict[product_variant_title]
                    else:
                        self.order_item_error(line_id, 'Variant mapping is not set for this item')
                        continue

                item.order_memo = self.order_notes
                req.add_item(item)

            aliexpress_order.set_info(req)

            result = aliexpress_order.getResponse(authrize=aliexpress_account.access_token)
            result = result.get('aliexpress_trade_buy_placeorder_response')

            if result and result.get('result') and result['result']['is_success']:
                aliexpress_order_id = ','.join(set([str(i) for i in result['result']['order_list']['number']]))

                try:
                    result = requests.post(
                        url=order_fulfill_url,
                        data=dict(store=self.store.id, order_id=self.order['id'], line_id=line_id,
                                  aliexpress_order_id=aliexpress_order_id, source_type=''),
                        headers=dict(Authorization=self.store.user.get_access_token())
                    )
                except Exception:
                    capture_exception()
                    self.order_item_error(line_id, f'Could not mark as ordered, AliExpress Order ID: {aliexpress_order_id}')
            else:
                error_message = 'Could not place order'
                if result:
                    error_code = result.get('result')
                    error_code = error_code.get('error_code') if error_code else None
                    if error_code == 'B_DROPSHIPPER_DELIVERY_ADDRESS_VALIDATE_FAIL':
                        error_message = 'Customer Shipping Address or Phone Number is not valid'
                    elif error_code == 'INVENTORY_HOLD_ERROR':
                        error_message = 'Could not place order because item is Out of stock'
                        self.order_item_error(line_id, error_message)
                        continue
                    elif error_code == 'BUY_LIMIT_RESOURCE_INSUFFICIENT':
                        error_message = "Could not place order because the item doesn't have sufficient available quantity."
                        self.order_item_error(line_id, error_message)
                        continue
                    elif error_code == 'DELIVERY_METHOD_NOT_EXIST':
                        error_message = 'Could not place order. This item does not ship to this area.'
                        self.order_item_error(line_id, error_message)
                        continue

                return self.order_error(error_message)

        return HttpResponse(status=200)


class AliexpressProduct():
    def __init__(self, product_id, aliexpress_account):
        self.product_id = product_id
        self.aliexpress_account = aliexpress_account

    def get_product_data(self):
        aliexpress_product_obj = FindProductViaApi()
        aliexpress_product_obj.set_app_info(API_KEY, API_SECRET)
        aliexpress_product_obj.product_id = self.product_id
        response = aliexpress_product_obj.getResponse(authrize=self.aliexpress_account.access_token)
        response = response['aliexpress_ds_product_get_response']
        return response.get('result')

    def get_product_sku_data(self, aliexpress_product_data):
        final_skus = {}
        variant_sku_data = aliexpress_product_data.get('ae_item_sku_info_dtos').get('ae_item_sku_info_d_t_o')
        if variant_sku_data is not None and len(variant_sku_data) > 0:
            for data in variant_sku_data:
                sku_list = data.get("ae_sku_property_dtos").get("ae_sku_property_d_t_o")
                ali_variant_title_list = [i.get('property_value_definition_name') or i.get('sku_property_value') for i in sku_list]
                ali_variant_title_list = sorted(ali_variant_title_list)
                ali_variant_title = '/'.join(ali_variant_title_list)
                final_skus[ali_variant_title] = data.get('id')
        return final_skus


class AliexpressApi(ApiResponseMixin):

    def post_order(self, request, user, data):
        storeType = data.get('store_type', 'shopify')
        if storeType == 'shopify':
            store = ShopifyStore.objects.get(id=data['store'])
        elif storeType == 'woo':
            store = WooStore.objects.get(id=data['store'])
        elif storeType == 'chq':
            store = CommerceHQStore.objects.get(id=data['store'])
        elif storeType == 'bigcommerce':
            store = BigCommerceStore.objects.get(id=data['store'])
        elif storeType == 'gkart':
            store = GrooveKartStore.objects.get(id=data['store'])

        permissions.user_can_view(user, store)

        order_notes = user.get_config('aliexpress_api_order_notes')

        try:
            helper = AliexpressFulfillHelper(store, data['order_id'], data['items'], data['shipping_address'], order_notes)
            if storeType == 'shopify':
                helper.fulfill_shopify_order()
            elif storeType == 'woo':
                helper.fulfill_woo_order()
            elif storeType == 'chq':
                helper.fulfill_chq_order()
            elif storeType == 'bigcommerce':
                helper.fulfill_bigcommerce_order()
            elif storeType == 'gkart':
                helper.fulfill_gkart_order()

        except AliexpressFulfillException:
            pass

        if helper.has_errors():
            return JsonResponse(helper.errors(), status=422)
        else:
            return self.api_success({'msg': helper.order_success_msg})

    def delete_account(self, request, user, data):
        account = AliexpressAccount.objects.get(id=data['account'])
        permissions.user_can_delete(user, account)

        account.delete()

        return self.api_success()

    def post_import_aliexpress_product(self, request, user, data):
        products = save_aliexpress_products(request, {
            user.id: {
                'product_id': data['product_id'],
                'currency': data['currency'],
                'store_ids': data['store_ids'],
                'publish': data['publish'],
            }
        })
        if products.get('errored', []):
            return self.api_error(products['errored'])

        return self.api_success()
