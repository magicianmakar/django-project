import json

from .aliexpress_api import RestApi
from .settings import API_KEY, API_SECRET

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
