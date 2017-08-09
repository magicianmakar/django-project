import re
import simplejson as json

from math import ceil

from django.db.models import Q
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404
from django.core.cache import cache, caches

from unidecode import unidecode
from raven.contrib.django.raven_compat.models import client as raven_client

from .models import CommerceHQStore, CommerceHQProduct, CommerceHQBoard
from shopified_core import permissions
from shopified_core.utils import safeInt, safeFloat
from shopified_core.shipping_helper import (
    load_uk_provincess,
    missing_province,
    country_from_code,
    province_from_code
)

import leadgalaxy.utils as leadgalaxy_utils


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


def get_chq_products_count(store):
    api_url = store.get_api_url('products')
    response = store.request.head(api_url)
    total_count = response.headers['X-Pagination-Total-Count']
    total = int(total_count)

    return total


def get_chq_products(store, page=1, limit=50, all_products=False):
    api_url = store.get_api_url('products')

    if not all_products:
        params = {'page': page, 'size': limit, 'expand': 'images,variants'}
        response = store.request.get(api_url, params=params)
        products = response.json()['items']

        for product in products:
            yield product
    else:
        limit = 200
        count = get_chq_products_count(store)

        if not count:
            return

        pages = int(ceil(count / float(limit)))
        for page in xrange(1, pages + 1):
            response = get_chq_products(store=store, page=page, limit=limit, all_products=False)
            products = response.json()['items']
            for product in products:
                yield product


def commercehq_products(request, post_per_page=25, sort=None, board=None, store='n'):
    store = request.GET.get('store', store)
    sort = request.GET.get('sort')

    user_stores = request.user.profile.get_chq_stores(flat=True)
    res = CommerceHQProduct.objects.select_related('store') \
                                   .filter(user=request.user.models_user) \
                                   .filter(Q(store__in=user_stores) | Q(store=None)) \
                                   .prefetch_related('commercehqboard_set')  # TODO: Optmize loading boards

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

    if board:
        res = res.filter(commercehqboard=board)
        permissions.user_can_view(request.user, get_object_or_404(CommerceHQBoard, id=board))

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

    for k in shipping_address.keys():
        if shipping_address[k] and type(shipping_address[k]) is unicode:
            customer_address[k] = unidecode(shipping_address[k])
        else:
            customer_address[k] = shipping_address[k]

    customer_address['address1'] = customer_address.get('street')
    customer_address['address2'] = customer_address.get('suite')
    customer_address['country_code'] = customer_address.get('country')
    customer_address['province_code'] = customer_address.get('state')

    customer_address['country'] = country_from_code(customer_address['country_code'])
    customer_address['province'] = province_from_code(customer_address['country_code'], customer_address['province_code'])

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

    elif customer_address['province'] == 'Virgin Islands':
        # Virgin Islands is a country in Aliexpress
        customer_address['province'] = 'VI'
        customer_address['country_code'] = 'VI'
        customer_address['country'] = 'Virgin Islands (U.S.)'

    elif customer_address['province'] == 'Guam':
        # Guam is a country in Aliexpress
        customer_address['province'] = 'GU'
        customer_address['country_code'] = 'GU'
        customer_address['country'] = 'Guam'

    customer_address['name'] = u'{} {}'.format(customer_address['first_name'], customer_address['last_name'])
    # customer_address['name'] = utils.ensure_title(customer_address['name'])

    # if customer_address['company']:
    #     customer_address['name'] = '{} - {}'.format(customer_address['name'],
    #                                                 customer_address['company'])
    return customer_address


def get_tracking_orders(store, tracker_orders):
    ids = []
    for i in tracker_orders:
        ids.append(str(i.order_id))

    if not len(ids):
        return tracker_orders

    rep = store.request.post(
        url=store.get_api_url('orders', 'search'),
        params={'size': 50},
        json={'id': ids}
    )

    rep.raise_for_status()

    orders = {}
    lines = {}
    orders_cache = {}

    for order in rep.json()['items']:
        orders[order['id']] = order
        for line in order['items']:
            line.update(line.get('data'))
            line.update(line.get('status'))
            line['image'] = (line.get('image') or '').replace('/uploads/', '/uploads/thumbnail_')

            lines['{}-{}'.format(order['id'], line['id'])] = line

        for fulfilment in order['fulfilments']:
            for item in fulfilment['items']:
                orders_cache['chq_fulfilments_{}_{}_{}'.format(store.id, order['id'], item['id'])] = fulfilment['id']

        for line in order['items']:
            orders_cache['chq_quantity_{}_{}_{}'.format(store.id, order['id'], line['id'])] = line['quantity']

    if len(orders_cache):
        caches['orders'].set_many(orders_cache, timeout=604800)

    new_tracker_orders = []
    for tracked in tracker_orders:
        tracked.order = orders.get(tracked.order_id)
        tracked.line = lines.get('{}-{}'.format(tracked.order_id, tracked.line_id))

        if tracked.line:
            if tracked.line.get('shipped') == tracked.line.get('quantity'):
                tracked.line['fulfillment_status'] = 'fulfilled'
            else:
                tracked.line['fulfillment_status'] = ''

            if tracked.commercehq_status != tracked.line['fulfillment_status']:
                tracked.commercehq_status = tracked.line['fulfillment_status']
                tracked.save()

        new_tracker_orders.append(tracked)

    return new_tracker_orders


def order_id_from_name(store, order_name, default=None):
    ''' Get Order ID from Order Name '''

    order_rx = store.user.get_config('order_number', {}).get(str(store.id), '[0-9]+')
    order_number = re.findall(order_rx, order_name)
    if not order_number:
        return default

    order_number = order_number[0]
    if len(order_number) > 7:
        # Order name should contain less than 7 digits
        return default

    params = {
        'status': 'any',
        'fulfillment_status': 'any',
        'financial_status': 'any',
        'fields': 'id',
        'name': order_name
    }

    params = {
        'id': order_name,
    }

    rep = store.request.post(
        url=store.get_api_url('orders', 'search'),
        json=params
    )

    if rep.ok:
        orders = rep.json()['items']

        if len(orders):
            return orders.pop()['id']

    return default


def format_chq_errors(e):
    if not hasattr(e, 'response') or e.response.status_code != 422:
        return 'Server Error'

    errors = e.response.json().get('errors') or e.response.json().get('message')

    if not errors:
        return 'Server Error'
    elif isinstance(errors, basestring):
        return errors

    msg = []
    for k, v in errors.items():
        if type(v) is list:
            error = u','.join(v)
        else:
            error = v

        if k == 'base':
            msg.append(error)
        else:
            msg.append(u'{}: {}'.format(k, error))

    return u' | '.join(msg)


def store_shipping_carriers(store):
    rep = store.request.get(store.get_api_url('shipping-carriers'), params={'size': 100})
    if rep.ok:
        return rep.json()['items']
    else:
        carriers = [
            {1: 'USPS'}, {2: 'UPS'}, {3: 'FedEx'}, {4: 'LaserShip'},
            {5: 'DHL US'}, {6: 'DHL Global'}, {7: 'Canada Post'}
        ]

        return map(lambda c: {'id': c.keys().pop(), 'title': c.values().pop()}, carriers)


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
            'id': re.sub(r'[^0-9]', '', self.request.GET.get('query') or ''),
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

        rep.raise_for_status()

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

        rep.raise_for_status()

        return rep.json()


def smart_board_by_board(user, board):
    for product in user.commercehqproduct_set.all():
        product_info = json.loads(product.data)
        product_info = {
            'title': product_info.get('title', '').lower(),
            'tags': product_info.get('tags', '').lower(),
            'type': product_info.get('type', '').lower(),
        }

        try:
            config = json.loads(board.config)
        except:
            continue

        product_added = False
        for j in ['title', 'tags', 'type']:
            if product_added:
                break

            if not len(config.get(j, '')) or not len(product_info[j]):
                continue

            for f in config.get(j, '').split(','):
                if f.lower() in product_info[j]:
                    board.products.add(product)
                    product_added = True

                    break

        if product_added:
            board.save()


def add_aftership_to_store_carriers(store):
    url = store.get_api_url('shipping-carriers')

    data = {
        'title': 'AfterShip',
        'url': 'http://track.aftership.com/',
        'is_deleted': False,
    }

    try:
        r = store.request.post(url=url, json=data)
        r.raise_for_status()

        return r.json()

    except:
        raven_client.captureException()
        return None


def get_shipping_carrier(shipping_carrier_name, store):
    cache_key = 'chq_shipping_carriers_{}_{}'.format(store.id, shipping_carrier_name)

    shipping_carriers = cache.get(cache_key)
    if shipping_carriers is not None:
        return shipping_carriers

    shipping_carriers_map = {}
    for i in store_shipping_carriers(store):
        shipping_carriers_map[i['title']] = i

    shipping_carrier = shipping_carriers_map.get(shipping_carrier_name, {})
    if not shipping_carrier:
        shipping_carrier = shipping_carriers_map.get('AfterShip', {})
        if not shipping_carrier:
            # Returns the newly added AfterShip shipping carrier
            aftership_carrier = add_aftership_to_store_carriers(store)
            if aftership_carrier:
                shipping_carrier = aftership_carrier

    if shipping_carrier:
        cache.set(cache_key, shipping_carrier, timeout=3600)

    return shipping_carrier


def check_notify_customer(source_tracking, user_config, shipping_carrier_name, last_shipment=False):
    is_usps = shipping_carrier_name == 'USPS'
    send_shipping_confirmation = user_config.get('send_shipping_confirmation', 'no')
    notify_customer = False

    if send_shipping_confirmation == 'yes':
        notify_customer = True
        validate_tracking_number = user_config.get('validate_tracking_number', False)
        is_valid_tracking_number = leadgalaxy_utils.is_valide_tracking_number(source_tracking)
        if validate_tracking_number and not is_valid_tracking_number and not is_usps:
            notify_customer = False

    elif send_shipping_confirmation == 'default':
        notify_customer = True if last_shipment else False

    return notify_customer


def cache_fulfillment_data(order_tracks, orders_max=None):
    """
    Caches order data of given `CommerceHQOrderTrack` instances
    """
    order_tracks = order_tracks[:orders_max] if orders_max else order_tracks
    stores = set()
    store_orders = {}

    for order_track in order_tracks:
        stores.add(order_track.store)
        store_orders.setdefault(order_track.store.id, set()).add(order_track.order_id)

    cache_data = {}
    for store in stores:
        order_ids = list(store_orders[store.id])

        r = store.request.post(
            url=store.get_api_url('orders', 'search'),
            json={'id': order_ids},
            params={
                'size': 200,
                'fields': 'id,items,fulfilments'
            },
        )

        r.raise_for_status()

        orders = r.json().get('items', [])

        for order in orders:
            total_quantity, total_shipped = 0, 0
            country = ''

            for order_item in order.get('items', []):
                total_quantity += order_item['status']['quantity']
                total_shipped += order_item['status']['shipped']

            if order.get('address') and order.get('address').get('shipping'):
                country = order['address']['shipping']['country']

            args = store.id, order['id']
            cache_data['chq_total_quantity_{}_{}'.format(*args)] = total_quantity
            cache_data['chq_total_shipped_{}_{}'.format(*args)] = total_shipped
            cache_data['chq_country_{}_{}'.format(*args)] = country

            for line in order.get('items', []):
                cache_data['chq_quantity_{}_{}_{}'.format(store.id, order['id'], line['data']['id'])] = line['status']['quantity']

            for fulfilment in order.get('fulfilments', []):
                for item in fulfilment.get('items', []):
                    args = store.id, order['id'], item['id']
                    cache_data['chq_fulfilments_{}_{}_{}'.format(*args)] = fulfilment['id']
                    cache_data['chq_quantity_{}_{}_{}'.format(*args)] = item['quantity']

    caches['orders'].set_many(cache_data, timeout=604800)

    return cache_data.keys()


def order_track_fulfillment(order_track, user_config=None):
    user_config = {} if user_config is None else user_config
    tracking_number = order_track.source_tracking

    kwargs = {
        'store_id': order_track.store_id,
        'order_id': order_track.order_id,
        'line_id': order_track.line_id
    }

    # Keys are set by `commercehq_core.utils.cache_fulfillment_data`
    fulfilment_id = caches['orders'].get('chq_fulfilments_{store_id}_{order_id}_{line_id}'.format(**kwargs))
    total_quantity = caches['orders'].get('chq_total_quantity_{store_id}_{order_id}'.format(**kwargs))
    total_shipped = caches['orders'].get('chq_total_shipped_{store_id}_{order_id}'.format(**kwargs))
    quantity = caches['orders'].get('chq_quantity_{store_id}_{order_id}_{line_id}'.format(**kwargs))
    country = caches['orders'].get('chq_country_{store_id}_{order_id}'.format(**kwargs))

    shipping_carrier_name = leadgalaxy_utils.shipping_carrier(tracking_number)

    if country and country == 'US':
        if leadgalaxy_utils.is_chinese_carrier(tracking_number) or leadgalaxy_utils.shipping_carrier(tracking_number) == 'USPS':
            shipping_carrier_name = 'USPS'

    shipping_carrier = get_shipping_carrier(shipping_carrier_name, order_track.store)

    if fulfilment_id is None:
        store = order_track.store
        rep = store.request.post(
            url=store.get_api_url('orders', order_track.order_id, 'fulfilments'),
            json={
                "items": [{
                    "id": order_track.line_id,
                    "quantity": caches['orders'].get('chq_quantity_{}_{}_{}'.format(store.id, order_track.order_id, order_track.line_id), 0),
                }]
            }
        )

        if rep.ok:
            for fulfilment in rep.json()['fulfilments']:
                for item in fulfilment['items']:
                    caches['orders'].set('chq_fulfilments_{}_{}_{}'.format(store.id, order_track.order_id, item['id']),
                                         fulfilment['id'], timeout=604800)

            fulfilment_id = caches['orders'].get('chq_fulfilments_{store_id}_{order_id}_{line_id}'.format(**kwargs))

    try:
        last_shipment = (total_quantity - total_shipped - quantity) == 0
    except:
        last_shipment = True

    notify_customer = check_notify_customer(tracking_number, user_config, shipping_carrier_name, last_shipment)

    return {
        'notify': notify_customer,
        'data': [{
            'fulfilment_id': fulfilment_id,
            'tracking_number': tracking_number,
            'shipping_carrier': shipping_carrier.get('id'),
            'items': [{
                'id': order_track.line_id,
                'quantity': quantity
            }]
        }],
    }
