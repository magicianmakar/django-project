import requests

from django.conf import settings
from django.core.cache import cache
from django.http import HttpResponse

from aliexpress_core.models import AliexpressAccount
from aliexpress_core.settings import API_KEY, API_SECRET
from aliexpress_core.utils import MaillingAddress
from aliexpress_core.utils import MaillingAddress, PlaceOrder, PlaceOrderRequest, ProductBaseItem
from leadgalaxy.models import ShopifyOrderTrack, ShopifyProduct, ShopifyStore
from leadgalaxy.utils import get_shopify_order
from shopified_core.mixins import ApiResponseMixin
from shopified_core.utils import app_link


def fulfill_shopify_order(store, order_id, line_ids, shipping_address):
    store = ShopifyStore.objects.get(id=store)
    order = get_shopify_order(store, order_id)

    order_tracks = {}
    for i in ShopifyOrderTrack.objects.filter(store=store, order_id=order['id']).defer('data'):
        order_tracks[f'{i.order_id}-{i.line_id}'] = i

    have_aliexpress = False

    for el in order['line_items']:
        if str(el['id']) not in line_ids:
            continue

        variant_id = el['variant_id']
        if not el['product_id']:
            if variant_id:
                product = ShopifyProduct.objects.filter(store=store, title=el['title'], shopify_id__gt=0).first()
            else:
                product = None
        else:
            product = ShopifyProduct.objects.filter(store=store, shopify_id=el['product_id']).first()

        shopify_order = order_tracks.get('{}-{}'.format(order['id'], el['id']))

        if not product or shopify_order or el['fulfillment_status'] == 'fulfilled' or (product and product.is_excluded):
            continue

        variant_id = product.get_real_variant_id(variant_id)
        supplier = product.get_supplier_for_variant(variant_id)
        if not product.have_supplier() or not supplier:
            continue

        elif supplier.is_aliexpress:
            if line_id:
                return fulfill_aliexpress_order(store, order['id'], el['id'])
            else:
                have_aliexpress = True

    if have_aliexpress:
        return fulfill_aliexpress_order(store, order['id'])
    else:
        return False


def fulfill_aliexpress_order(store, order_id, line_id=None):
    from leadgalaxy.views import OrdersView

    if not API_SECRET:
        return 'Service API is not set'

    if not store.user.aliexpress_account.count():
        return 'Aliexpress Account is not connected'

    orders = OrdersView().find_orders(store=store, order_id=order_id, line_id=line_id)

    results = []
    for items in orders:
        result = do_fulfill_aliexpress_order(items, store, order_id, line_id)

    results.append(result)
    return HttpResponse(status=200)


def do_fulfill_aliexpress_order(orders, store, order_id, line_id=None):
    from leadgalaxy.api import ShopifyStoreApi

    order_item = []
    for order in orders['items']:
        order_data = ShopifyStoreApi().get_order_data(None, store.user, {'order': order['order_data'], 'no_format': 1})
        order_item.append(order_data)

    aliexpress_order = PlaceOrder()
    aliexpress_order.set_app_info(API_KEY, API_SECRET)

    shipping_address = order_data['shipping_address']
    address = MaillingAddress()
    address.contact_person = shipping_address['name']
    address.full_name = shipping_address['name']
    address.address = shipping_address['address1']
    address.address2 = shipping_address['address2']
    address.city = shipping_address['city']
    address.province = shipping_address['province']
    address.zip = shipping_address['zip']
    address.country = shipping_address['country_code']
    address.phone_country = order_data['order']['phoneCountry']
    address.mobile_no = order_data['order']['phone']

    req = PlaceOrderRequest()
    req.setAddress(address)

    product_list = {}
    temp = []
    for order in order_item:
        if str(order['supplier_id']) in product_list:
            temp = product_list[str(order['supplier_id'])]
        else:
            temp = []
        temp.append(order)
        product_list[str(order['supplier_id'])] = temp

    for key in product_list:
        req.product_items = []
        for i in product_list[key]:
            item = ProductBaseItem()
            item.product_count = i['quantity']
            item.product_id = i['source_id']
            item.sku_attr = ';'.join([f"{v['sku']}#{v['title'] or ''}".strip('#') for v in i['variant']])
            # item.logistics_service_name = "DHL"  # TODO: handle shipping method
            item.order_memo = i['order']['note']
            req.add_item(item)
        aliexpress_order.set_info(req)
        aliexpress_account = AliexpressAccount.objects.filter(user=store.user).first()

        result = aliexpress_order.getResponse(authrize=aliexpress_account.access_token)
        result = result.get('aliexpress_trade_buy_placeorder_response')
        if result and result.get('result') and result['result']['is_success']:
            aliexpress_order_id = ','.join(set([str(i) for i in result['result']['order_list']['number']]))
        for line_id in orders['line_id']:
            try:
                req = requests.post(
                    url=app_link('api/order-fulfill'),
                    data=dict(store=store.id, order_id=order_id, line_id=line_id, aliexpress_order_id=aliexpress_order_id, source_type=''),
                    headers=dict(Authorization=store.user.get_access_token())
                )
            except Exception:
                pass

        return HttpResponse(status=200)


class AliexpressApi(ApiResponseMixin):

    def post_order(self, request, user, data):
        pprint(data)
        return self.api_success()
