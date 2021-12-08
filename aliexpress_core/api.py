
import requests
from collections import defaultdict

from django.http import HttpResponse, JsonResponse

from aliexpress_core.models import AliexpressAccount
from aliexpress_core.settings import API_KEY, API_SECRET
from aliexpress_core.utils import MaillingAddress, PlaceOrder, PlaceOrderRequest, ProductBaseItem
from leadgalaxy.models import ShopifyOrderTrack, ShopifyProduct, ShopifyStore
from leadgalaxy.utils import get_shopify_order
from lib.exceptions import capture_exception
from shopified_core import permissions
from shopified_core.exceptions import AliexpressFulfillException
from shopified_core.mixins import ApiResponseMixin
from shopified_core.utils import app_link


class AliexpressFulfillHelper():
    def __init__(self, store, order_id, items, shipping_address):
        self.store = store
        self.order_id = order_id
        self.items = items
        self.shipping_address = shipping_address

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
            return self.order_error('Order have no items that need fulfillements')

        self.items = need_fulfill_items

        self.fulfill_aliexpress_order()

    def fulfill_aliexpress_order(self):
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

        address.phone_country, address.mobile_no = self.shipping_address['phone'].split('-')

        req = PlaceOrderRequest()
        req.setAddress(address)

        for line_id, line_item in self.items.items():
            req.product_items = []
            item = ProductBaseItem()
            item.product_count = line_item['quantity']
            item.product_id = line_item['source_id']
            item.sku_attr = ';'.join([f"{v['sku']}#{v['title'] or ''}".strip('#') for v in line_item['variant']])
            # item.logistics_service_name = "DHL"  # TODO: handle shipping method
            item.order_memo = 'No Invoice'  # TODO: Memo
            req.add_item(item)

            aliexpress_order.set_info(req)
            aliexpress_account = AliexpressAccount.objects.filter(user=self.store.user).first()

            result = aliexpress_order.getResponse(authrize=aliexpress_account.access_token)
            result = result.get('aliexpress_trade_buy_placeorder_response')

            if result and result.get('result') and result['result']['is_success']:
                aliexpress_order_id = ','.join(set([str(i) for i in result['result']['order_list']['number']]))

                try:
                    result = requests.post(
                        url=app_link('api/order-fulfill'),
                        data=dict(store=self.store.id, order_id=self.order['id'], line_id=line_id,
                                  aliexpress_order_id=aliexpress_order_id, source_type=''),
                        headers=dict(Authorization=self.store.user.get_access_token())
                    )
                except Exception:
                    capture_exception()
                    return self.order_error('Could not mark as ordered')
            else:
                error_message = 'Could not place order'
                if result:
                    error_code = result.get('result')
                    error_code = error_code.get('error_code') if error_code else None
                    if error_code == 'B_DROPSHIPPER_DELIVERY_ADDRESS_VALIDATE_FAIL':
                        error_message = 'Customer Shipping Address or Phone Number is not valid'

                return self.order_error(error_message)

        return HttpResponse(status=200)


class AliexpressApi(ApiResponseMixin):

    def post_order(self, request, user, data):
        store = ShopifyStore.objects.get(id=data['store'])
        permissions.user_can_view(user, store)

        try:
            helper = AliexpressFulfillHelper(store, data['order_id'], data['items'], data['shipping_address'])
            helper.fulfill_shopify_order()

        except AliexpressFulfillException:
            pass

        if helper.has_errors():
            return JsonResponse(helper.errors(), status=422)
        else:
            return self.api_success()

    def delete_account(self, request, user, data):
        account = AliexpressAccount.objects.get(id=data['account'])
        permissions.user_can_delete(user, account)

        account.delete()

        return self.api_success()
