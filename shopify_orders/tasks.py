from django.http.response import HttpResponse
import requests

from aliexpress_core.models import AliexpressAccount

from app.celery_base import celery_app, CaptureFailure
from leadgalaxy.templatetags.template_helper import app_link

from lib.exceptions import capture_exception

from aliexpress_core.settings import API_KEY, API_SECRET
from aliexpress_core.utils import MaillingAddress, PlaceOrder, OrderInfo, PlaceOrderRequest, ProductBaseItem
from leadgalaxy.models import ShopifyStore, ShopifyProduct, ShopifyOrderTrack
from shopify_orders.utils import OrderErrorsCheck, update_elasticsearch_shopify_order
from shopify_orders.models import ShopifyOrder
from groovekart_core.models import GrooveKartStore
from woocommerce_core.models import WooStore
from bigcommerce_core.models import BigCommerceStore
from commercehq_core.models import CommerceHQStore
import json


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
    is_bundle = False
    if orders.get('bundle', False):
        is_bundle = True

    order_item = []
    for order in orders['items']:
        order_data = ShopifyStoreApi().get_order_data(None, store.user, {'order': order['order_data'], 'no_format': 1})
        order_item.append(order_data)

    if is_bundle:
        if len(order_item) > 0:
            order_data = order_item[0]
            order_item = order_data['products']
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
        if is_bundle:
            supplier_id = order['source_id']
        else:
            supplier_id = order['supplier_id']
        if str(supplier_id) in product_list:
            temp = product_list[str(supplier_id)]
        else:
            temp = []
        temp.append(order)
        product_list[str(supplier_id)] = temp

    for key in product_list:
        req.product_items = []
        for i in product_list[key]:
            item = ProductBaseItem()
            item.product_count = i['quantity']
            item.product_id = i['source_id']
            temp_variants = i.get('variants') or i.get('variant')
            item.sku_attr = ';'.join([f"{v['sku']}#{v['title'] or ''}".strip('#') for v in temp_variants])
            # item.logistics_service_name = "DHL"  # TODO: handle shipping method
            # item.order_memo = i['order']['note'] or order_data['order']['note']
            req.add_item(item)
        aliexpress_order.set_info(req)
        aliexpress_account = AliexpressAccount.objects.filter(user=store.user).first()

        result = aliexpress_order.getResponse(authrize=aliexpress_account.access_token)
        result = result.get('aliexpress_trade_buy_placeorder_response')
        if result and result.get('result') and result['result']['is_success']:
            aliexpress_order_id = ','.join(set([str(i) for i in result['result']['order_list']['number']]))
        for line_id in orders['line_id']:
            try:
                request = requests.post(
                    url=app_link('api/order-fulfill'),
                    data=dict(store=store.id, order_id=order_id, line_id=line_id, aliexpress_order_id=aliexpress_order_id, source_type=''),
                    headers=dict(Authorization=store.user.get_access_token())
                )
                print(request)
            except Exception:
                pass

    return HttpResponse(status=200)


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


@celery_app.task(base=CaptureFailure, bind=True, ignore_result=True)
def get_order_info_via_api(self, order, source_id, store_id, store_type=None, user=None):

    STATUS_MAP = {
        "PLACE_ORDER_SUCCESS": "Awaiting Payment",
        "IN_CANCEL": "Awaiting Cancellation",
        "WAIT_SELLER_SEND_GOODS": "Awaiting Shipment",
        "SELLER_PART_SEND_GOODS": "Partial Shipment",
        "WAIT_BUYER_ACCEPT_GOODS": "Awaiting delivery",
        "WAIT_GROUP_SUCCESS": "Pending operation success",
        "FINISH": "Order Completed",
        "IN_ISSUE": "Dispute Orders",
        "IN_FROZEN": "Frozen Orders",
        "WAIT_SELLER_EXAMINE_MONEY": "Payment not yet confirmed",
        "RISK_CONTROL": "Payment being verified",
        "IN_PRESELL_PROMOTION": "Promotion is on",
        "FUND_PROCESSING": "Fund Processing",

        "BUYER_NO_SHOW": "Pickup cancelled buyer no show",
        "BUYER_REJECTED": "Pickup cancelled buyer rejected",
        "DELIVERED": "Delivered",
        "DIRECT_DEBIT": "Direct Debit",
        "EXTERNAL_WALLET": "Processed by PayPal",
        "IN_TRANSIT": "In transit",
        "MANIFEST": "Shipping Info Received",
        "NO_PICKUP_INSTRUCTIONS_AVAILABLE": "No pickup instruction available",
        "NOT_PAID": "Not Paid",
        "NOT_SHIPPED": "Item is not shipped",
        "SHIPPED": "Shipped",
        "OUT_OF_STOCK": "Out of stock",
        "PENDING_MERCHANT_CONFIRMATION": "Order is being prepared",
        "PICKED_UP": "Picked up",
        "PICKUP_CANCELLED_BUYER_NO_SHOW": "Pickup cancelled buyer no show",
        "PICKUP_CANCELLED_BUYER_REJECTED": "Pickup cancelled buyer rejected",
        "PICKUP_CANCELLED_OUT_OF_STOCK": "Out of stock",
        "READY_FOR_PICKUP": "Ready for pickup",
        "SHIPPING_INFO_RECEIVED": "Shipping info received",

        "D_PENDING_PAYMENT": "Pending Payment",
        "D_PAID": "Confirmed Payment",
        "D_PENDING_SHIPMENT": "Pending Shipment",
        "D_SHIPPED": "Shipped"
    }
    if store_type is not None:
        if store_type == 'shopify':
            store = ShopifyStore.objects.get(id=store_id)
        if store_type == 'gkart':
            store = GrooveKartStore.objects.get(id=store_id)
        elif store_type == 'woo':
            store = WooStore.objects.get(id=store_id)
        elif store_type == 'bigcommerce':
            store = BigCommerceStore.objects.get(id=store_id)
        elif store_type == 'chq':
            store = CommerceHQStore.objects.get(id=store_id)

    if user is None:
        user = store.user

    if not API_SECRET:
        return 'Service API is not set'
    if not user.aliexpress_account.count():
        return 'Aliexpress Account is not connected'

    aliexpress_order_details = OrderInfo()
    aliexpress_order_details.set_app_info(API_KEY, API_SECRET)

    aliexpress_order_details.single_order_query = json.dumps({"order_id": source_id})

    aliexpress_account = AliexpressAccount.objects.filter(user=user).first()

    try:
        result = aliexpress_order_details.getResponse(authrize=aliexpress_account.access_token)

        fulfillment_data = {}
        order_details = {}
        order_data = result.get('aliexpress_trade_ds_order_get_response')
        if order_data is None:
            return None
        order_data = order_data.get('result')
        fulfillment_data['tracking_number'] = ''
        tracking_number_obj = order_data.get('logistics_info_list').get('aeop_order_logistics_info')
        if tracking_number_obj is not None:
            fulfillment_data['tracking_number'] = tracking_number_obj[0]['logistics_no']
        fulfillment_data['end_reason'] = ''
        fulfillment_data['status'] = order_data['order_status']
        fulfillment_data['orderStatus'] = order_data['order_status']
        fulfillment_data['order_status'] = STATUS_MAP[order_data['order_status']]

        # product data starts here
        product_data = order_data.get("child_order_list", None)
        total_product_price = 0
        if product_data is not None:
            product_data = product_data.get("aeop_child_order_info")
            for product in product_data:
                product_qty = product['product_count']
                product_price = product['product_price']['amount']
                total_product_price = total_product_price + (float(product_price) * product_qty)

        cost = {}
        cost['total'] = order_data['order_amount']['amount']
        cost['currency'] = order_data['order_amount']['currency_code']
        cost['shipping'] = ''
        cost['products'] = str(total_product_price) if total_product_price > 0 else ''
        order_details['cost'] = cost
        fulfillment_data['order_details'] = order_details
        return fulfillment_data
    except Exception as e:
        return {
            'error_msg': f'AliExpress: {e.message}',
            'error_code': e.errorcode,
            'sub_code': e.subcode,
        }
