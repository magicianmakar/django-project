import json
import re
from unidecode import unidecode

from django.core.cache import cache
from django.db.models import Q
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404
from raven.contrib.django.raven_compat.models import client as raven_client

from shopified_core import permissions
from shopified_core.utils import safe_int, safe_float, decode_params
from shopified_core.shipping_helper import (
    load_uk_provincess,
    province_from_code
)

from .models import GrooveKartStore, GrooveKartProduct, GrooveKartBoard


def filter_products(res, fdata):
    if fdata.get('title'):
        title = decode_params(fdata.get('title'))
        res = res.filter(title__icontains=title)

    if fdata.get('price_min') or fdata.get('price_max'):
        min_price = safe_float(fdata.get('price_min'), -1)
        max_price = safe_float(fdata.get('price_max'), -1)

        if (min_price > 0 and max_price > 0):
            res = res.filter(price__gte=min_price, price__lte=max_price)

        elif (min_price > 0):
            res = res.filter(price__gte=min_price)

        elif (max_price > 0):
            res = res.filter(price__lte=max_price)

    if fdata.get('type'):
        res = res.filter(product_type__icontains=fdata.get('type'))

    if fdata.get('tag'):
        res = res.filter(tags__icontains=fdata.get('tag'))

    if fdata.get('vendor'):
        res = res.filter(default_supplier__supplier_name__icontains=fdata.get('vendor'))

    return res


def get_gkart_products(store, page=1, limit=50, product_ids=None):
    api_url = store.get_api_url('list_products.json')

    params = {'page': page, 'limit': limit}

    if product_ids:
        params['ids'] = ','.join(product_ids)
        api_url = store.get_api_url('search_products.json')

    r = store.request.post(api_url, json=params)
    return r.json()['products']


def groovekart_products(request, post_per_page=25, sort=None, board=None, store='n'):
    store = request.GET.get('store', store)
    sort = request.GET.get('sort')

    user_stores = request.user.profile.get_gkart_stores(flat=True)
    res = GrooveKartProduct.objects.select_related('store') \
                           .filter(user=request.user.models_user) \
                           .filter(Q(store__in=user_stores) | Q(store=None))

    if store:
        if store == 'c':  # connected
            res = res.exclude(source_id=0)
        elif store == 'n':  # non-connected
            res = res.filter(source_id=0)

            in_store = safe_int(request.GET.get('in'))
            if in_store:
                in_store = get_object_or_404(GrooveKartStore, id=in_store)
                res = res.filter(store=in_store)

                permissions.user_can_view(request.user, in_store)
        else:
            store = get_object_or_404(GrooveKartStore, id=store)
            res = res.filter(source_id__gt=0, store=store)

            permissions.user_can_view(request.user, store)

    if board:
        res = res.filter(boards=board)
        permissions.user_can_view(request.user, get_object_or_404(GrooveKartBoard, id=board))

    res = filter_products(res, request.GET)

    if sort:
        if re.match(r'^-?(title|price)$', sort):
            res = res.order_by(sort)

    return res


def format_gkart_errors(e):
    if not hasattr(e, 'response'):
        return 'Server Error'

    return e.response.json().get('error', '')


def get_store_from_request(request):
    store = None
    stores = request.user.profile.get_gkart_stores()

    if request.GET.get('shop'):
        try:
            store = stores.get(shop=request.GET.get('shop'))
        except (GrooveKartStore.DoesNotExist, GrooveKartStore.MultipleObjectsReturned):
            pass

    if not store and request.GET.get('store'):
        store = get_object_or_404(stores, id=safe_int(request.GET.get('store')))

    if store:
        permissions.user_can_view(request.user, store)
        request.session['last_store'] = store.id
    else:
        try:
            if 'last_store' in request.session:
                store = stores.get(id=request.session['last_store'])
                permissions.user_can_view(request.user, store)

        except (PermissionDenied, GrooveKartStore.DoesNotExist):
            store = None

    if not store:
        store = stores.first()

    return store


def store_shipping_carriers(store):
    carriers = [
        {7: 'USPS'},
    ]

    return [{'id': list(c.keys()).pop(), 'title': list(c.values()).pop()} for c in carriers]


def get_shipping_carrier_name(store, carrier_id):
    shipping_carriers = store_shipping_carriers(store)
    for carrier in shipping_carriers:
        if carrier['id'] == carrier_id:
            return carrier['title']


def gkart_customer_address(order):
    customer_address = {}

    shipping_address = order.get('shipping_address', {})

    customer_address['first_name'] = shipping_address.get('first_name')
    customer_address['last_name'] = shipping_address.get('last_name')
    customer_address['name'] = f"{customer_address['first_name']} {customer_address['last_name']}"
    customer_address['address1'] = shipping_address.get('address1', '')
    customer_address['city'] = shipping_address.get('city', '')
    customer_address['country_code'] = shipping_address.get('country_code', '')
    customer_address['province_code'] = shipping_address.get('province', '')
    customer_address['zip'] = shipping_address.get('zip', '')
    customer_address['country'] = shipping_address.get('country', '')
    customer_address['province'] = province_from_code(customer_address['country_code'], customer_address['province_code'])

    for key in list(customer_address.keys()):
        if customer_address[key] is str:
            customer_address[key] = unidecode(customer_address[key])

    if not customer_address.get('province'):
        if customer_address['country'] == 'United Kingdom' and customer_address['city']:
            province = load_uk_provincess().get(customer_address['city'].lower().strip(), '')

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

    if customer_address['country_code'] == 'CA':
        if customer_address.get('zip'):
            customer_address['zip'] = re.sub(r'[\n\r\t ]', '', customer_address['zip']).upper().strip()

        if customer_address['province'] == 'Newfoundland':
            customer_address['province'] = 'Newfoundland and Labrador'

    if customer_address['country'] == 'United Kingdom':
        if customer_address.get('zip'):
            if not re.findall(r'^([0-9A-Za-z]{2,4}\s[0-9A-Za-z]{3})$', customer_address['zip']):
                customer_address['zip'] = re.sub(r'(.+)([0-9A-Za-z]{3})$', r'\1 \2', customer_address['zip'])

    if customer_address['country_code'] == 'PL':
        if customer_address.get('zip'):
            customer_address['zip'] = re.sub(r'[\n\r\t\._ -]', '', customer_address['zip'])

    return customer_address


def set_gkart_order_note(store, order_id, note):
    api_url = store.get_api_url('orders.json')
    r = store.request.post(api_url, json={
        'order_id': safe_int(order_id),
        'action': 'add_note',
        'note': note
    })
    r.raise_for_status()

    return r.ok


def order_id_from_name(store, order_reference, default=None):
    ''' Get Order ID from Order Name '''

    order_rx = store.user.get_config('order_number', {}).get(str(store.id), '[0-9]+')
    order_number = re.findall(order_rx, order_reference)

    return order_number if order_number else default


def get_tracking_orders(store, tracker_orders):
    # ids = [str(track.order_id) for track in tracker_orders]
    orders = {}
    lines = {}
    page = 1
    limit = 50

    while page:
        params = {
            'offset': limit * (page - 1),
            'limit': limit,
            # 'ids': ','.join(ids),
        }
        r = store.request.post(store.get_api_url('orders.json'), json=params)

        if r.ok:
            result = r.json()
            if 'orders' not in result:
                break

            for order in result['orders']:
                orders[order['id']] = order

                for line in order.get('line_items', []):
                    lines['{}-{}'.format(order['id'], line['id'])] = line

            page += 1

        if r.status_code == 404:
            break

        r.raise_for_status()

    new_tracker_orders = []

    for tracked in tracker_orders:
        tracked.order = orders.get(str(tracked.order_id))
        tracked.line = lines.get('{}-{}'.format(tracked.order_id, tracked.line_id))

        # TODO: mark only the fulfilled item as fulfilled
        # This marks the entire order items as fulfilled once a tracking number is sent for one item
        if tracked.line:
            fulfillment_status = 'fulfilled' if tracked.order.get('trackings') else None
            tracked.line['fulfillment_status'] = fulfillment_status

            if tracked.groovekart_status != fulfillment_status:
                tracked.groovekart_status = fulfillment_status
                tracked.save()

        new_tracker_orders.append(tracked)

    return new_tracker_orders


class OrderListQuery(object):
    def __init__(self, store, params=None):
        self._endpoint = 'orders.json'
        self._store = store
        self._params = {} if params is None else params

    def items(self):
        url = self._store.get_api_url(self._endpoint)
        r = self._store.request.post(url, json=self._params)

        try:
            if r.ok:
                result = r.json()
                # Empty list of orders returns with Error key
                if 'Error' in result:
                    return []

                if 'orders' in result:
                    result = result['orders']

                # Single order search returns as dict
                if not isinstance(result, list):
                    if result.get('reference') is None:  # Order Not Found
                        result = []
                    else:
                        result = [result]

                return result
            elif r.status_code == 404:
                return []
            else:
                r.raise_for_status()
        except:
            raven_client.captureException()
            return []

    def count(self):
        if self._params.get('order_id'):
            return 1

        url = self._store.get_api_url(self._endpoint)
        r = self._store.request.post(url, json={
            **self._params,
            'action': 'orders_count'
        })
        r.raise_for_status()

        try:
            return r.json()['orders_count']
        except:
            raven_client.captureException()
            return 0

    def update_params(self, update):
        self._params.update(update)

        return self


class OrderListPaginator(Paginator):
    def page(self, number):
        number = self.validate_number(number)
        params = {'offset': self.per_page * (number - 1), 'limit': self.per_page}
        # `self.object_list` is an `OrderListQuery` instance
        items = list(self.object_list.update_params(params).items())

        return self._get_page(items, number, self)


class GrooveKartOrderUpdater:

    def __init__(self, store=None, order_id=None):
        self.store = store
        self.order_id = order_id

        self.notes = []

    def add_note(self, n):
        self.notes.append(n)

    def mark_as_ordered_note(self, line_id, source_id, track):
        source = 'Aliexpress'

        if track:
            url = track.get_source_url()
            if track.source_type == 'ebay':
                source = 'eBay'
        else:
            url = 'http://trade.aliexpress.com/order_detail.htm?orderId={}'.format(source_id)

        note = '{} Order ID: {}\n{}'.format(source, source_id, url)

        if line_id:
            note = '{}\nOrder Line: #{}'.format(note, line_id)

        self.add_note(note)

    def save_changes(self, add=True):
        with cache.lock('updater_lock_{}_{}'.format(self.store.id, self.order_id), timeout=15):
            self._do_save_changes(add=add)

    def _do_save_changes(self, add=True):
        if self.notes:
            new_note = '\n'.join(self.notes)
            set_gkart_order_note(self.store, self.order_id, new_note)

    def delay_save(self, countdown=None):
        from .tasks import order_save_changes

        order_save_changes.apply_async(
            args=[self.toJSON()],
            countdown=countdown
        )

    def toJSON(self):
        return json.dumps({
            "notes": self.notes,
            "order": self.order_id,
            "store": self.store.id,
        }, sort_keys=True, indent=4)

    def fromJSON(self, data):
        if type(data) is not dict:
            data = json.loads(data)

        self.store = GrooveKartStore.objects.get(id=data.get("store"))
        self.order_id = data.get("order")

        self.notes = data.get("notes")