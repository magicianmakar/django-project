import json
from decimal import Decimal

from django.contrib.auth.models import User
from django.shortcuts import get_object_or_404

from leadgalaxy.models import PriceMarkupRule
from leadgalaxy.utils import format_shopify_send_to_store
from lib.exceptions import capture_exception
from shopified_core.utils import get_store_api

from .aliexpress_api import RestApi
from .settings import DEFAULT_USER

TOKEN = '50002001035rqggaZzI2hlT9Uxf9iFv4tTuHJdwgyHwSADa1e7759d89ORfe4gfBGlF8'


class MaillingAddress:
    contact_person = None
    full_name = None
    address2 = None
    address = None
    city = None
    province = None
    zip = None
    country = None
    mobile_no = None
    phone_country = None

    locale = 'en_US'

    tax_number = None
    cpf = None
    passport_no = None
    passport_no_date = None
    passport_organization = None

    def to_dict(self):
        items = {}
        for key, value in self.__dict__.items():
            # if value:
            items[key] = value

        return items


class ProductBaseItem:
    logistics_service_name = None
    order_memo = None
    product_count = None
    product_id = None
    sku_attr = None

    def to_dict(self):
        items = {}
        for key, value in self.__dict__.items():
            # if value:
            items[key] = value

        return items


class PlaceOrderRequest:
    logistics_address = None
    product_items = []

    def setAddress(self, address):
        self.logistics_address = address

    def add_item(self, item):
        self.product_items.append(item)

    def to_dict(self):
        return {
            'logistics_address': self.logistics_address.to_dict(),
            'product_items': [i.to_dict() for i in self.product_items]
        }

    def to_json(self):
        return json.dumps(self.to_dict(), indent=0).replace('\n', '')


class FindProduct(RestApi):
    def __init__(self, domain='gw.api.taobao.com', port=80):
        RestApi.__init__(self, domain, port)

    def getapiname(self):
        return 'aliexpress.postproduct.redefining.findaeproductbyidfordropshipper'


class FindProductViaApi(RestApi):
    def __init__(self, domain='gw.api.taobao.com', port=80):
        RestApi.__init__(self, domain, port)

    def getapiname(self):
        return 'aliexpress.ds.product.get'


class ShippingInfo(RestApi):
    def __init__(self, domain='gw.api.taobao.com', port=80):
        RestApi.__init__(self, domain, port)

    def getapiname(self):
        return 'aliexpress.logistics.buyer.freight.calculate'

    def set_info(self, info):
        self.param_aeop_freight_calculate_for_buyer_d_t_o = info


class OrderInfo(RestApi):
    def __init__(self, domain='gw.api.taobao.com', port=80):
        RestApi.__init__(self, domain, port)

    def getapiname(self):
        return 'aliexpress.trade.ds.order.get'


class PlaceOrder(RestApi):
    def __init__(self, domain='gw.api.taobao.com', port=80):
        RestApi.__init__(self, domain, port)

    def getapiname(self):
        return 'aliexpress.trade.buy.placeorder'

    def set_info(self, info):
        self.param_place_order_request4_open_api_d_t_o = info.to_json()


def get_aliexpress_account(user=None):
    account = None
    if user:
        account = user.models_user.aliexpress_account.first()
    if not account:
        default_user = User.objects.get(username=DEFAULT_USER)
        account = default_user.models_user.aliexpress_account.first()

    return account


def get_store_data(user):
    shopify_stores = user.profile.get_shopify_stores()
    chq_stores = user.profile.get_chq_stores()
    gkart_stores = user.profile.get_gkart_stores()
    woo_stores = user.profile.get_woo_stores()
    big_stores = user.profile.get_bigcommerce_stores()
    ebay_stores = user.profile.get_ebay_stores(do_sync=True)
    fb_stores = user.profile.get_fb_stores()
    google_stores = user.profile.get_google_stores()

    return dict(
        shopify=[{'id': s.id, 'value': s.title} for s in shopify_stores],
        chq=[{'id': s.id, 'value': s.title} for s in chq_stores],
        gkart=[{'id': s.id, 'value': s.title} for s in gkart_stores],
        woo=[{'id': s.id, 'value': s.title} for s in woo_stores],
        ebay=[{'id': s.id, 'value': s.title} for s in ebay_stores],
        fb=[{'id': s.id, 'value': s.title} for s in fb_stores],
        google=[{'id': s.id, 'value': s.title} for s in google_stores],
        bigcommerce=[{'id': s.id, 'value': s.title} for s in big_stores],
    )


def get_description_simplified(description):
    from bs4 import BeautifulSoup

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
    from prints.utils import get_price_markup

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


def save_aliexpress_products(request, products_data):
    result_products = {'saved': [], 'errored': []}
    for user_id, product_data in products_data.items():
        try:
            user = get_object_or_404(User, id=user_id)
        except:
            capture_exception()

        aliexpress_account = get_aliexpress_account(user=user)

        api_product = aliexpress_account.get_ds_product_details(product_data['product_id'], currency=product_data['currency'])
        if api_product.get('error', None):
            result_products['errored'].append(api_product['error'])
            continue

        api_product = apply_user_config(user, api_product)

        # will be {store_type}_{store_id}
        for import_to in product_data['store_ids']:
            store_type, store_id = import_to.split('_')

            data = {
                'data': json.dumps(api_product),
                'original': json.dumps(api_product),
                'store': store_id,
                'notes': '',
                'activate': len(import_to) == 1,
                'b': True,
            }

            StoreAPI = get_store_api(store_type)
            if store_type == 'shopify':
                StoreAPI.target = 'save-for-later'
                response = StoreAPI.post_save_for_later(request, user, data)
            else:
                StoreAPI.target = 'product-save'
                response = StoreAPI.post_product_save(request, user, data)

            result = json.loads(response.content.decode("utf-8"))
            product = result['product']

            if product_data['publish']:  # Send to Store
                if store_type == 'shopify':
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
                    data = {
                        'product': product['id'],
                        'store': store_id,
                        'publish': 'true' if user.get_config('make_visisble') else 'false',
                    }
                    StoreAPI.target = 'product-export'
                    StoreAPI.post_product_export(request, user, data)

        result_products['saved'].append(product)
    return result_products
