
import json
import phonenumbers
import requests
from collections import defaultdict

from django.core.cache import cache
from django.http import HttpResponse, JsonResponse
from django.shortcuts import reverse

from aliexpress_core.models import AliexpressAccount
from aliexpress_core.settings import API_KEY, API_SECRET
from aliexpress_core.utils import FindProductViaApi, MaillingAddress, PlaceOrder, PlaceOrderRequest, ProductBaseItem, ShippingInfo
from bigcommerce_core.models import BigCommerceOrderTrack, BigCommerceProduct, BigCommerceStore
from bigcommerce_core.utils import get_bigcommerce_order_data, get_order_product_data
from commercehq_core.models import CommerceHQOrderTrack, CommerceHQProduct, CommerceHQStore
from commercehq_core.utils import get_chq_order
from groovekart_core.models import GrooveKartOrderTrack, GrooveKartProduct, GrooveKartStore
from groovekart_core.utils import get_gkart_order
from leadgalaxy.models import ShopifyOrderTrack, ShopifyProduct, ShopifyStore
from leadgalaxy.utils import get_shopify_order
from lib.aliexpress_api import TopException
from lib.exceptions import capture_exception
from shopified_core import permissions
from shopified_core.exceptions import AliexpressFulfillException
from shopified_core.mixins import ApiResponseMixin
from shopified_core.utils import app_link, safe_float
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
        self.session_expired_msg = 'Session expired. Please reconnect your AliExpress account'
        self.aliexpress_settings_link = app_link(f"{reverse('settings')}#aliexpress")

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
        # cache_key = f"aliexpress_drop_ship_product_details_{product_id}"
        # aliexpress_product_result = cache.get(cache_key, {})
        product_data = AliexpressProduct(product_id, aliexpress_account)
        aliexpress_product_result = product_data.get_product_data()
        if aliexpress_product_result is None:
            return None
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
                else:
                    if temp_variants[0] == 'Default Title' or temp_variants[0] == 'Default':
                        sku_attr = ''
                    else:
                        sku_attr = ';'.join([f"{v['sku']}#{v['title'] or ''}".strip('#') for v in temp_variants])
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
            return self.set_order_success_msg('No items to order')

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
            if el['data'].get('variant'):
                variant_id = el['data']['variant']['id']
            else:
                variant_id = None
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
            return self.set_order_success_msg('No items to order')

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
            return self.set_order_success_msg('No items to order')

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
            return self.set_order_success_msg('No items to order')

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
            return self.set_order_success_msg('No items to order')

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
        address.province = self.shipping_address['province'].strip()
        if address.province.lower() == 'n/a' or not address.province:
            address.province = 'Other'
        address.zip = self.shipping_address['zip']
        address.country = self.shipping_address['country_code']

        if not self.shipping_address['phone'].startswith('+'):
            dialing_code = '+' + str(phonenumbers.country_code_for_region(self.shipping_address['country_code']))
            order_phone_number = dialing_code + '-' + self.shipping_address['phone']
        else:
            order_phone_number = self.shipping_address['phone']

        try:
            parsed = phonenumbers.parse(order_phone_number)
            address.phone_country = '+' + str(parsed.country_code)
            if '0000000000' in order_phone_number:
                address.mobile_no = '0000000000'
            else:
                address.mobile_no = parsed.national_number
        except Exception:
            return self.order_error("Invalid Phone number. Please enter a valid number")

        req = PlaceOrderRequest()
        req.setAddress(address)

        aliexpress_account = AliexpressAccount.objects.filter(user=self.store.user).first()
        if not aliexpress_account:
            settings_link = app_link(f"{reverse('settings')}#aliexpress")
            return self.order_error(f'<span>No AliExpress account found. Click <a href="{settings_link}" target="_blank">here</a> to connect</span>')

        aliexpress_variant_sku_dict = ''
        product_list = {}
        temp = []
        # combine orders with supplier id as key
        for line_id, line_item in self.items.items():
            if line_item['is_bundle']:
                product_list[line_item['line_id']] = [line_item]
            else:
                supplier_id = line_item['supplier_id']
                if str(supplier_id) in product_list:
                    temp = product_list[str(supplier_id)]
                else:
                    temp = []
                temp.append(line_item)
                product_list[str(supplier_id)] = temp

        for key in product_list:
            req.product_items = []
            line_items_array = []
            for line_item in product_list[key]:
                line_items_array.append(line_item['line_id'])
                aliexpress_variant_sku_dict = ''
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

                    # Get Shipping Method from Advanced Variant Mapping
                    shipping_mapping = line_item['shipping_method']
                    if shipping_mapping is not None:
                        if shipping_mapping.get('method') is not None:
                            item.logistics_service_name = shipping_mapping.get('method')
                    if not item.logistics_service_name:  # Get Shipping methods list from Settings under AliExpress tab
                        priority_service_list = []  # saves the list of Shipping methods in order of priority from Settings under AliExpress tab
                        service = ''
                        config = json.loads(self.store.user.profile.config)
                        for i in range(1, 5):
                            method_key = f'aliexpress_shipping_method_{i}'
                            shipping_method = config.get(method_key)
                            if shipping_method:
                                priority_service_list.append(shipping_method)

                        shipping_obj = ShippingMethods(line_item, self.shipping_address, aliexpress_account)
                        shipping_data = shipping_obj.get_shipping_data()

                        # Match the Shipping data with the list saved in settings. Exit the loops when the first match is found
                        # In case no match is found, we don't set the Shipping method & default shipping is assigned.
                        if shipping_data is not None:
                            for service_name in priority_service_list:
                                if service:
                                    break
                                for data in shipping_data:
                                    if service_name == data['service_name']:
                                        service = data['service_name']
                                        item.logistics_service_name = data['service_name']
                                        break
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
                        try:
                            aliexpress_variant_sku_dict = self.ds_product_data(line_item['source_id'], aliexpress_account)
                        except TopException as e:
                            if e.errorcode == 27 and e.message.strip().lower() == 'invalid session':
                                sess_msg = self.session_expired_msg
                                return self.order_error(f'<span>{sess_msg} <a href="{self.aliexpress_settings_link}" target="_blank">here</a></span>')
                            else:
                                return self.order_error(e.message)
                        if aliexpress_variant_sku_dict is None:
                            self.order_item_error(line_id, 'This item is discontinued in AliExpress.')
                            line_items_array.pop()
                            continue

                        if aliexpress_variant_sku_dict == '<none>':
                            item.sku_attr = ''
                        else:
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
                                line_items_array.pop()
                                continue

                    item.order_memo = self.order_notes
                    new_line = '\n'
                    if bool(self.store.user.models_user.get_config('order_custom_line_attr')) and line_item['order'].get('item_note'):
                        item.order_memo = f"{item.order_memo}{new_line}{line_item['order']['item_note']}"
                    req.add_item(item)

                aliexpress_order.set_info(req)

            # check for duplicate line items
            items_sku = []
            duplicate_item = False
            for i, obj in enumerate(req.product_items):
                if obj.sku_attr:
                    sku_str = f"{obj.sku_attr}#{obj.product_id}"
                else:
                    sku_str = obj.product_id

                if sku_str in items_sku:
                    duplicate_item = True
                    try:
                        index = items_sku.index(obj.sku_attr)
                    except:
                        index = items_sku.index(obj.product_id)
                    popped = req.product_items.pop()
                    req.product_items[index].product_count = req.product_items[index].product_count + popped.product_count
                items_sku.append(sku_str)
            if duplicate_item:
                aliexpress_order.set_info(req)
            # #######End of check########

            if len(req.product_items) == 0:
                return self.order_error('No items to order')
            try:
                result = aliexpress_order.getResponse(authrize=aliexpress_account.access_token)
            except TopException as e:
                if e.errorcode == 27 and e.message.strip().lower() == 'invalid session':
                    session_msg = self.session_expired_msg
                    return self.order_error(f'<span>{session_msg} <a href="{self.aliexpress_settings_link}" target="_blank">here</a></span>')
                else:
                    return self.order_error(e.message)

            result = result.get('aliexpress_trade_buy_placeorder_response')

            if result and result.get('result') and result['result']['is_success']:
                aliexpress_order_id = ','.join(set([str(i) for i in result['result']['order_list']['number']]))

                for line_id in line_items_array:
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
                    if error_code == 'USER_ACCOUNT_DISABLED':
                        error_message = 'Your AliExpress Account is disabled. Please contact AliExpress support.'
                        self.order_error(error_message)
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
                    elif error_code == 'BLACKLIST_BUYER_IN_LIST':
                        error_message = 'Your supplier has blacklisted you. Please contact your supplier or find another supplier.'
                        self.order_item_error(line_id, error_message)
                        continue

                return self.order_error(error_message)

        return HttpResponse(status=200)


class AliexpressProduct():
    def __init__(self, product_id, aliexpress_account):
        self.product_id = product_id
        self.aliexpress_account = aliexpress_account

    def get_product_data(self):
        cache_key = f"aliexpress_drop_ship_product_details_{self.product_id}"
        aliexpress_product_result = cache.get(cache_key, {})

        if not aliexpress_product_result:
            aliexpress_product_obj = FindProductViaApi()
            aliexpress_product_obj.set_app_info(API_KEY, API_SECRET)
            aliexpress_product_obj.product_id = self.product_id
            aliexpress_product_obj.target_currency = 'USD'
            response = aliexpress_product_obj.getResponse(authrize=self.aliexpress_account.access_token)
            response = response['aliexpress_ds_product_get_response']
            cache.set(cache_key, response.get('result'), timeout=600)
            aliexpress_product_result = response.get('result')
        return aliexpress_product_result

    def get_product_sku_data(self, aliexpress_product_data):
        final_skus = {}

        if not aliexpress_product_data:
            return final_skus

        variant_sku_data = aliexpress_product_data.get('ae_item_sku_info_dtos').get('ae_item_sku_info_d_t_o')
        if variant_sku_data is not None and len(variant_sku_data) > 0:
            if len(variant_sku_data) == 1:
                sku_id = variant_sku_data[0].get('id')
                if sku_id == '<none>':
                    return sku_id

            for data in variant_sku_data:
                try:
                    sku_list = data.get("ae_sku_property_dtos").get("ae_sku_property_d_t_o")
                    ali_variant_title_list = [i.get('property_value_definition_name') or i.get('sku_property_value') for i in sku_list]
                    ali_variant_title_list = sorted(ali_variant_title_list)
                    ali_variant_title = '/'.join(ali_variant_title_list)
                    final_skus[ali_variant_title] = data.get('id')

                    # for products imported via API
                    alternate_variant_title_list = [i.get('sku_property_value') for i in sku_list]
                    alternate_variant_title_list = sorted(alternate_variant_title_list)
                    alternate_variant_title = '/'.join(alternate_variant_title_list)
                    final_skus[alternate_variant_title] = data.get('id')
                except Exception:
                    continue
        return final_skus

    def get_data(self, aliexpress_product_data):
        final_skus = {}
        variant_sku_data = aliexpress_product_data.get('ae_item_sku_info_dtos').get('ae_item_sku_info_d_t_o')
        if variant_sku_data is not None and len(variant_sku_data) > 0:
            if len(variant_sku_data) == 1:
                sku_id = variant_sku_data[0].get('id')
                if sku_id == '<none>':
                    return {
                        'sku': variant_sku_data[0].get('id'),
                        'price': safe_float(variant_sku_data[0].get('sku_price')),
                        'stock': variant_sku_data[0].get('sku_available_stock'),
                        'variant': False
                    }

            for data in variant_sku_data:
                try:
                    sku_list = data.get("ae_sku_property_dtos").get("ae_sku_property_d_t_o")
                    ali_variant_title_list = [i.get('property_value_definition_name') or i.get('sku_property_value') for i in sku_list]
                    ali_variant_title_list = sorted(ali_variant_title_list)
                    ali_variant_title = (' / '.join(ali_variant_title_list)).lower()
                    final_skus[ali_variant_title] = {
                        'sku': data.get('id'),
                        'price': safe_float(data.get('sku_price')),
                        'stock': data.get('sku_available_stock'),
                        'variant': True
                    }

                    # for products imported via API
                    alternate_variant_title_list = [i.get('sku_property_value') for i in sku_list]
                    alternate_variant_title_list = sorted(alternate_variant_title_list)
                    alternate_variant_title = (' / '.join(alternate_variant_title_list)).lower()
                    final_skus[alternate_variant_title] = {
                        'sku': data.get('id'),
                        'price': data.get('sku_price'),
                        'stock': data.get('sku_available_stock'),
                        'variant': True
                    }

                except Exception:
                    continue
        return final_skus


class ShippingMethods():
    def __init__(self, line_item, shipping_address, aliexpress_account):
        self.product_id = line_item['source_id']
        self.quantity = line_item['quantity']
        self.aliexpress_account = aliexpress_account
        self.shipping_address = shipping_address
        self.variant = line_item.get('variant', {})

    def get_shipping_data(self):
        aliexpress_obj = ShippingInfo()
        aliexpress_obj.set_app_info(API_KEY, API_SECRET)

        send_goods_country_code = 'CN'
        for v in self.variant:
            if isinstance(v, dict):
                if v.get('title'):
                    if v.get('title').lower().strip() == 'united states':
                        send_goods_country_code = 'US'
                        break
            elif isinstance(v, str):
                if v.lower().strip() == 'united states':
                    send_goods_country_code = 'US'
                    break
            else:
                return None

        data = {
            "product_id": self.product_id,
            "product_num": self.quantity,
            "country_code": self.shipping_address['country_code'],
            "provice_code": self.shipping_address['province_code'],
            "city_code": self.shipping_address['zip'],
            "send_goods_country_code": send_goods_country_code
        }
        aliexpress_obj.set_info(json.dumps(data, indent=0))
        try:
            result = aliexpress_obj.getResponse(authrize=self.aliexpress_account.access_token)
            shipping_data = result['aliexpress_logistics_buyer_freight_calculate_response']['result']
            if shipping_data.get('success'):
                shipping_data = shipping_data['aeop_freight_calculate_result_for_buyer_d_t_o_list']['aeop_freight_calculate_result_for_buyer_dto']
                return shipping_data
            else:
                return None
        except:
            return None


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

        order_notes = user.models_user.get_config('aliexpress_api_order_notes')

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

    def post_import_aliexpress_data(self, request, user, data):
        shipping_data = self.import_shipping_method(user, data)
        product_data = self.import_ali_product_data(user, data)
        return self.api_success({**shipping_data, **product_data})

    def import_shipping_method(self, user, data):
        try:
            SHIPPING_DATA = {
                "CAINIAO_CONSOLIDATION_AE": "Aliexpress Direct (UAE)",
                "CAINIAO_CONSOLIDATION_BR": "Aliexpress Direct (Brazil)",
                "CAINIAO_PREMIUM": "AliExpress Premium Shipping",
                "CAINIAO_ECONOMY": "AliExpress Saver Shipping",
                "CAINIAO_STANDARD": "AliExpress Standard Shipping",
                "ARAMEX": "ARAMEX",
                "ASENDIA_US": "ASENDIA (USA)",
                "AUSPOST": "Australia Post",
                "BSC_ECONOMY_SG": "BSC Special Economy",
                "BSC_STANDARD_SG": "BSC Special Standard",
                "CAINIAO_EXPEDITED_ECONOMY": "Cainiao Expedited Economy",
                "AE_CAINIAO_STANDARD": "Cainiao Expedited Standard",
                "CAINIAO_STANDARD_HEAVY": "Cainiao Heavy Parcel Line",
                "CAINIAO_ECONOMY_SG": "Cainiao Saver Shipping For Special Goods",
                "CAINIAO_STANDARD_SG": "Cainiao Standard For Special Goods",
                "CAINIAO_SUPER_ECONOMY": "Cainiao Super Economy",
                "CAINIAO_SUPER_ECONOMY_SG": "Cainiao Super Economy for Special Goods",
                "AE_CN_SUPER_ECONOMY_G": "Cainiao Super Economy Global",
                "CAINIAO_OVERSEAS_WH_EXPPL": "Cainiao Warehouse Express Shipping",
                "CPAP": "China Post Air Parcel",
                "YANWEN_JYT": "China Post Ordinary Small Packet Plus",
                "CPAM": "China Post Registered Air Mail",
                "CORREIOS_BR": "Correios Brazil",
                "DEUTSCHE_POST": "Deutsche Post",
                "DHL": "DHL",
                "DHLECOM": "DHL e-commerce",
                "EMS": "EMS",
                "E_EMS": "e-EMS",
                "EMS_ZX_ZX_US": "ePacket",
                "FEDEX": "Fedex IP",
                "FEDEX_IE": "Fedex IE",
                "FLYT": "Flyt Express",
                "FLYT_ECONOMY_SG": "Flyt Special Economy",
                "GLS_FR": "GLS France",
                "GLS_ES": "GLS Spain",
                "LAPOSTE": "La Poste",
                "MEEST": "Meest",
                "POSTKR": "POSTKR",
                "POST_NL": "PostNL",
                "RUSSIAN_POST": "Russian Post",
                "SF_EPARCEL_OM": "SF Economic Air Mail",
                "SF_EPARCEL": "SF eParcel",
                "SF": "SF Express",
                "SGP": "Singapore Post",
                "SUNYOU_RM": "SunYou",
                "SUNYOU_ECONOMY": "SunYou Economic Air Mail",
                "SUNYOU_ECONOMY_SG": "SunYou Special Economy",
                "SHUNYOU_STANDARD_SG": "SunYou Special Standard",
                "CHP": "Swiss Post",
                "TNT": "TNT",
                "LAOPOST": "TOPYOU",
                "TOPYOU_ECONOMY_SG": "TOPYOU Special Economy",
                "PTT": "Turkey Post",
                "UBI": "UBI",
                "UPS": "UPS",
                "UPS_US": "UPS (USA)",
                "UPSE": "UPS Expedited",
                "USPS": "USPS",
                "YANWEN_ECONOMY": "Yanwen Economic Air Mail",
                "YANWEN_ECONOMY_SG": "Yanwen Special Economy",
                "YANWEN_AM": "Yanwen Special Standard",
                "Other": "Sellers Shipping Method"
            }

            cache_key = f"aliexpress_shipping_method_{data['order']['store']}_{data['order']['order_id']}_{data['order']['order_data']['source_id']}"
            aliexpress_shipping_result = cache.get(cache_key, {})
            if aliexpress_shipping_result:
                return aliexpress_shipping_result

            priority_service_list = []  # saves the list of Shipping methods in order of priority from Settings under AliExpress tab
            service = ''
            config = json.loads(user.profile.config)
            for i in range(1, 5):
                method_key = f'aliexpress_shipping_method_{i}'
                shipping_method = config.get(method_key)
                if shipping_method:
                    priority_service_list.append(shipping_method)
            aliexpress_account = AliexpressAccount.objects.filter(user=user.models_user).first()

            try:
                variant_title = "/".join(data['order']['order_data']['variant'])
            except:
                title = []
                for v in data['order']['order_data']['variant']:
                    title.append(v['title'])
                variant_title = "/".join(title)
            line_item = {
                'source_id': data['order']['order_data']['source_id'],
                'quantity': data['order']['order_data']['quantity'],
                'variant': variant_title
            }
            shipping_obj = ShippingMethods(line_item, data['order']['order_data']['shipping_address'], aliexpress_account)
            shipping_data = shipping_obj.get_shipping_data()
            if shipping_data is None:
                return {'data': {}}
            shipping_services = [{
                'amount': '',
                'service_code': '',
                'service_name': 'Select Shipping'
            }]
            for data in shipping_data:
                if not data.get('error_code'):
                    temp = {
                        'amount': data.get('freight').get('amount'),
                        'service_code': data.get('service_name'),
                        'service_name': SHIPPING_DATA.get(data.get('service_name')) or data.get('service_name')
                    }
                    shipping_services.append(temp)
                    if shipping_data is not None:
                        for service_name in priority_service_list:
                            if service:
                                break
                            for data in shipping_data:
                                if service_name == data.get('service_name'):
                                    service = data['service_name']
                                    break
            cache.set(cache_key, {'data': shipping_services, 'shipping_setting': service}, timeout=600)

            return {'data': shipping_services, 'shipping_setting': service}
        except:
            shipping_services = {}
            return {'data': shipping_services, 'shipping_setting': ''}

    def import_ali_product_data(self, user, data):
        try:
            product_id = data['order']['order_data']['source_id']
            aliexpress_account = AliexpressAccount.objects.filter(user=user.models_user).first()
            product_data = AliexpressProduct(product_id, aliexpress_account)
            aliexpress_product_result = product_data.get_product_data()
            p_data = product_data.get_data(aliexpress_product_result)
            if 'variant' in p_data:
                return p_data
            try:
                variant = [v['title'].lower() for v in data['order']['order_data']['variant']]
            except:
                variant = map(lambda title: title.strip().lower(), data['order']['order_data']['variant'])  # if item variant list contain spaces
                variant = list(variant)
            variant = sorted(variant)
            variant = (' / '.join(variant)).lower()
            return p_data[variant]
        except:
            return {'sku': '', 'price': '', 'stock': '', 'variant': False}
