import re

from django.db.models import Q
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404

from unidecode import unidecode

from .models import CommerceHQStore, CommerceHQProduct
from shopified_core import permissions
from shopified_core.utils import safeInt, safeFloat
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


def commercehq_products(request, post_per_page=25, sort=None, board=None, load_boards=False):
    store = request.GET.get('store')
    sort = request.GET.get('sort')

    user_stores = request.user.profile.get_chq_stores(flat=True)
    res = CommerceHQProduct.objects.select_related('store') \
                                   .filter(user=request.user.models_user)

    if request.user.is_subuser:
        res = res.filter(store__in=user_stores)
    else:
        res = res.filter(Q(store__in=user_stores) | Q(store=None))

    if store:
        if store == 'c':  # connected
            res = res.exclude(source_id=0)
        elif store == 'n':  # non-connected
            res = res.filter(source_id=0)

            in_store = safeInt(request.GET.get('in'))
            if in_store:
                in_store = get_object_or_404(CommerceHQStore, id=in_store)
                res = res.filter(store=in_store)

                permissions.user_can_view(request.user, in_store)
        else:
            store = get_object_or_404(CommerceHQStore, id=store)
            res = res.filter(source_id__gt=0, store=store)

            permissions.user_can_view(request.user, store)

    # if board:
        # res = res.filter(shopifyboard=board)
        # permissions.user_can_view(request.user, get_object_or_404(ShopifyBoard, id=board))

    res = filter_products(res, request.GET)

    if sort:
        if re.match(r'^-?(title|price)$', sort):
            res = res.order_by(sort)

    return res


def filter_products(res, fdata):
    if fdata.get('title'):
        res = res.filter(title__icontains=fdata.get('title'))

    if fdata.get('price_min') or fdata.get('price_max'):
        min_price = safeFloat(fdata.get('price_min'), -1)
        max_price = safeFloat(fdata.get('price_max'), -1)

        if (min_price > 0 and max_price > 0):
            res = res.filter(price__gte=min_price, price__lte=max_price)

        elif (min_price > 0):
            res = res.filter(price__gte=min_price)

        elif (max_price > 0):
            res = res.filter(price__lte=max_price)

    if fdata.get('type'):
        res = res.filter(product_type__icontains=fdata.get('type'))

    if fdata.get('tag'):
        res = res.filter(tag__icontains=fdata.get('tag'))

    if fdata.get('vendor'):
        res = res.filter(default_supplier__supplier_name__icontains=fdata.get('vendor'))

    return res


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
    request = None
    size = 20

    _products = None

    def set_size(self, size):
        self.size = size

    def set_current_page(self, page):
        self.current_page = int(page)

    def set_query(self, query):
        self.query = query

    def set_store(self, store):
        self.store = store

    def set_request(self, r):
        self.request = r

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

    def _request_filters(self):
        filters = {
            'order_number': self.request.GET.get('query'),
            'status': self.request.GET.get('fulfillment'),
            'paid': self.request.GET.get('financial'),
        }

        for k, v in filters.items():
            if not v:
                del filters[k]
            elif ',' in v:
                filters[k] = v.split(',')

        return filters

    def _orders_request(self):
        params = {
            'size': self.per_page,
            'page': getattr(self, 'current_page', 1),
            'sort': self.request.GET.get('sort', '!order_date'),
            # 'expand': 'all',
        }

        params.update(self._request_filters())

        filters = self._request_filters()
        if filters:
            rep = self.store.request.post(
                url=self.store.get_api_url('orders', 'search'),
                params=params,
                json=filters
            )
        else:
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

        filters = self._request_filters()
        if filters:
            rep = self.store.request.post(
                url=self.store.get_api_url('orders', 'search'),
                params=params,
                json=filters
            )
        else:
            rep = self.store.request.get(
                url=self.store.get_api_url('orders'),
                params=params
            )

        return rep.json()
