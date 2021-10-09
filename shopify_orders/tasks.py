

import requests

from aliexpress_core.models import AliexpressAccount

from app.celery_base import celery_app, CaptureFailure
from leadgalaxy.templatetags.template_helper import app_link

from lib.exceptions import capture_exception

from aliexpress_core.settings import API_KEY, API_SECRET
from aliexpress_core.utils import MaillingAddress, PlaceOrder, PlaceOrderRequest, ProductBaseItem
from leadgalaxy.models import ShopifyStore, ShopifyProduct, ShopifyOrderTrack
from shopify_orders.utils import OrderErrorsCheck, update_elasticsearch_shopify_order
from shopify_orders.models import ShopifyOrder


@celery_app.task(base=CaptureFailure, bind=True, ignore_result=True)
def fulfill_shopify_order_line(self, store_id, order, customer_address, line_id=None):
    """ Try to Auto fulfill a Shopify Order if an item within this product support it

    This function look at each item in the order and try to detect lines that need to be
    auto fulfilled

    Args:
        store_id: Shopify Store ID
        order: Shopify Order Data (recieved from order create/update webhook)
        customer_address: address from shopify_customer_address
        line_id: (optional) Fulfil only this line ID
    """

    store = ShopifyStore.objects.get(id=store_id)

    order_tracks = {}
    for i in ShopifyOrderTrack.objects.filter(store=store, order_id=order['id']).defer('data'):
        order_tracks['{}-{}'.format(i.order_id, i.line_id)] = i

    have_aliexpress = False

    for el in order['line_items']:
        if line_id and int(line_id) != el['id']:
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
                return fulfill_aliexpress_order(store, order['id'], line_id)
            else:
                have_aliexpress = True

    if have_aliexpress:
        return fulfill_aliexpress_order(store, order['id'])
    else:
        return False


def fulfill_aliexpress_order(store, order_id, line_id=None):
    if not API_SECRET:
        return 'Service API is not set'

    if not store.user.aliexpress_account.count():
        return 'Aliexpress Account is not connected'

    req = requests.get(
        url=app_link('orders'),
        params=dict(store=store.id, query_order=order_id, line_id=line_id, bulk_queue=1, live=1),
        headers=dict(Authorization=store.user.get_access_token())
    )

    orders = req.json()
    results = []
    for order in orders['orders']:
        order_data = req = requests.get(
            url=app_link('api/order-data'),
            params=dict(order=order['order_data']),
            headers=dict(Authorization=store.user.get_access_token())
        ).json()

        results.append(do_fulfill_aliexpress_order(order, order_data, store, order_id, line_id))

    return all(results)


def do_fulfill_aliexpress_order(order, order_data, store, order_id, line_id=None):
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

    item = ProductBaseItem()
    item.product_count = order_data['quantity']
    item.product_id = order_data['source_id']
    item.sku_attr = ';'.join([f"{v['sku']}#{v['title'] or ''}".strip('#') for v in order_data['variant']])
    # item.logistics_service_name = "DHL"  # TODO: handle shipping method
    item.order_memo = order_data['order']['note']
    req.add_item(item)

    aliexpress_order.set_info(req)

    aliexpress_account = AliexpressAccount.objects.filter(user=store.user).first()

    result = aliexpress_order.getResponse(authrize=aliexpress_account.access_token)
    result = result.get('aliexpress_trade_buy_placeorder_response')
    if result and result.get('result') and result['result']['is_success']:
        aliexpress_order_id = ','.join(set([str(i) for i in result['result']['order_list']['number']]))

        req = requests.post(
            url=app_link('api/order-fulfill'),
            data=dict(store=store.id, order_id=order_id, line_id=line_id, aliexpress_order_id=aliexpress_order_id, source_type=''),
            headers=dict(Authorization=store.user.get_access_token())
        )

        return req.ok


@celery_app.task(base=CaptureFailure, bind=True, ignore_result=True)
def check_track_errors(self, track_id):
    try:
        track = ShopifyOrderTrack.objects.get(id=track_id)
    except ShopifyOrderTrack.DoesNotExist:
        return

    orders_check = OrderErrorsCheck()
    orders_check.check(track, commit=True)


@celery_app.task(base=CaptureFailure, bind=True, ignore_result=True)
def index_shopify_order(self, order_pk):
    """
    Re-index the passed order

    Args:
        order_pk (int): ShopifyOrder primary key id
    """

    try:
        order = ShopifyOrder.objects.get(id=order_pk)
        update_elasticsearch_shopify_order(order)

    except ShopifyOrderTrack.DoesNotExist:
        pass

    except:
        capture_exception()
