from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404

from unidecode import unidecode

from .models import CommerceHQStore
from shopified_core import permissions
from shopified_core.utils import safeInt
from shopified_core.province_helper import load_uk_provincess, missing_province


def get_store_from_request(request):
    """
    Return CommerceHQStore from based on `store` value or last saved store
    """

    store = None
    stores = request.user.profile.get_chq_stores()

    if request.GET.get('shop'):
        try:
            store = stores.get(shop=request.GET.get('shop'))
        except (CommerceHQStore.DoesNotExist, CommerceHQStore.MultipleObjectsReturned):
            pass

    if not store and request.GET.get('store'):
        store = get_object_or_404(stores, id=safeInt(request.GET.get('store')))

    if store:
        permissions.user_can_view(request.user, store)
        request.session['last_store'] = store.id
    else:
        try:
            if 'last_store' in request.session:
                store = stores.get(id=request.session['last_store'])
                permissions.user_can_view(request.user, store)

        except (PermissionDenied, CommerceHQStore.DoesNotExist):
            store = None

    if not store:
        store = stores.first()

    return store


def chq_customer_address(order):
    customer_address = {}
    shipping_address = order['shipping_address']
    address_map = {
        'street': 'address1',
        'suite': 'address2',
        'country': 'country_code',
    }

    for k in shipping_address.keys():
        if shipping_address[k] and type(shipping_address[k]) is unicode:
            customer_address[k] = unidecode(shipping_address[k])
        else:
            customer_address[k] = shipping_address[k]

        if k in address_map:
            customer_address[address_map[k]] = customer_address[k]

    if not customer_address.get('province'):
        if customer_address['country'] == 'United Kingdom' and customer_address['city']:
            province = load_uk_provincess().get(customer_address['city'].lower().strip(), '')
            if not province:
                missing_province(customer_address['city'])

            customer_address['province'] = province
        else:
            customer_address['province'] = customer_address['country_code']

    elif customer_address['province'] == 'Washington DC':
        customer_address['province'] = 'Washington'

    elif customer_address['province'] == 'Puerto Rico':
        # Puerto Rico is a country in Aliexpress
        customer_address['province'] = 'PR'
        customer_address['country_code'] = 'PR'
        customer_address['country'] = 'Puerto Rico'

    # customer_address['name'] = utils.ensure_title(customer_address['name'])

    # if customer_address['company']:
        # customer_address['name'] = '{} - {}'.format(customer_address['name'],
        #                                             customer_address['company'])
    return customer_address


class CommerceHQOrdersPaginator(Paginator):
    query = None
    store = None
    extra_filter = None
    size = 2

    _products = None

    def set_size(self, size):
        self.size = size

    def set_current_page(self, page):
        self.current_page = int(page)

    def set_query(self, query):
        self.query = query

    def set_extra_filter(self, extra_filter):
        if len(extra_filter):
            self.extra_filter = extra_filter

    def set_store(self, store):
        self.store = store

    def page(self, number):
        """
        Returns a Page object for the given 1-based page number.
        """

        number = self.validate_number(number)
        bottom = (number - 1) * self.per_page
        top = bottom + self.per_page
        if top + self.orphans >= self.count:
            top = self.count

        self.set_current_page(number)

        if self._count > 0 and (not self._products or number != self.current_page):
            self._get_products()

        return self._get_page(self._products, number, self)

    def page_range(self):
        """
        Returns a 1-based range of pages for iterating through within
        a template for loop.
        """
        page_count = self.num_pages

        pages = range(max(1, self.current_page - 5), self.current_page) + range(self.current_page, min(page_count + 1, self.current_page + 5))
        if 1 not in pages:
            pages = [1, None] + pages

        if page_count not in pages:
            pages = pages + [None, page_count]

        return pages

    def _get_products(self):
        rep = self._orders_request()
        self._products = rep['items']

    def _get_product_count(self):
        """
        Returns the total number of objects, across all pages.
        """
        if self._count is None:
            rep = self._orders_count_request()
            self._count = rep['_meta']['totalCount']
            self._num_pages = rep['_meta']['pageCount']

        return self._count

    count = property(_get_product_count)

    def _get_num_pages(self):
        if self._num_pages is None:
            rep = self._orders_count_request()
            self._count = rep['_meta']['totalCount']
            self._num_pages = rep['_meta']['pageCount']

        return self._num_pages

    num_pages = property(_get_num_pages)

    def _orders_request(self):
        params = {
            'size': self.per_page,
            'page': getattr(self, 'current_page', 1),
            # 'expand': 'all',
        }

        if (self.extra_filter):
            params.update(self.extra_filter)

        rep = self.store.request.get(
            url=self.store.get_api_url('orders'),
            params=params
        )

        return rep.json()

    def _orders_count_request(self):
        params = {
            'size': self.per_page,
            'page': 1,
            'fields': 'id'
        }

        if (self.extra_filter):
            params.update(self.extra_filter)

        rep = self.store.request.get(
            url=self.store.get_api_url('orders'),
            params=params
        )

        return rep.json()
