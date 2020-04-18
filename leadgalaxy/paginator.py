
from django.core.cache import cache
from django.core.paginator import Paginator, Page
from django.utils.crypto import get_random_string

from leadgalaxy.shopify import ShopifyAPI
from shopified_core.utils import safe_str


class ShopifyOrderPaginator(Paginator):
    reverse_order = False
    query = None
    page_info = None
    page_encode_len = 8

    def set_store(self, store):
        self.store = store
        self.api = ShopifyAPI(self.store)

    def set_filter(self, status, fulfillment, financial, created_at_start=None, created_at_end=None):
        self.status = status
        self.fulfillment = fulfillment
        self.financial = financial
        self.created_at_start = created_at_start
        self.created_at_end = created_at_end

    def set_order_limit(self, limit):
        self.order_limit = limit

    def set_page_info(self, info):
        decoded_info = self.decode_page_info(info)
        if decoded_info:
            self.page_info = decoded_info

    def set_reverse_order(self, reverse_order):
        self.reverse_order = reverse_order

    def set_query(self, query):
        self.query = query

    def page(self, number):
        orders, next_page_info, previous_page_info = self.api.get_orders(
            params=self._get_order_params(),
            page_info=self.page_info)

        return ShopifyOrderPage(orders, number, self, next_page_info, previous_page_info)

    def orders_count(self):
        return self.api.get_orders_count(params=self._get_order_params())

    def validate_number(self, number):
        return True

    def _get_order_params(self):
        if self.reverse_order:
            sorting = 'asc'
        else:
            sorting = 'desc'

        params = {
            'limit': self.order_limit,
            'status': self.status,
            'fulfillment_status': self.fulfillment,
            'financial_status': self.financial,
            'order': 'processed_at {}'.format(sorting)
        }

        if self.created_at_start:
            params['created_at_min'] = self.created_at_start

        if self.created_at_end:
            params['created_at_max'] = self.created_at_end

        if self.query:
            params['ids'] = self.query

        return params

    def encode_page_info(self, info):
        while True:
            page_id = get_random_string(self.page_encode_len)
            if not cache.get(f'page_info_{page_id}'):
                cache.set(f'page_info_{page_id}', info, timeout=259200)

                return page_id

    def decode_page_info(self, info):
        if len(safe_str(info)) == self.page_encode_len:
            return cache.get(f'page_info_{info}')


class ShopifyOrderPage(Page):
    is_infinte = True

    next_page_info = None
    previous_page_info = None

    def __init__(self, object_list, number, paginator, next_page_info, previous_page_info):
        super().__init__(object_list, number, paginator)

        self.next_page_info = next_page_info
        self.previous_page_info = previous_page_info

    def __repr__(self):
        return "<Page %s>" % self.number

    def has_next(self):
        return self.next_page_info if self.next_page_info else False

    def next_page_number(self):
        return self.paginator.encode_page_info(self.next_page_info)

    def has_previous(self):
        return self.previous_page_info if self.previous_page_info else False

    def previous_page_number(self):
        return self.paginator.encode_page_info(self.previous_page_info)
