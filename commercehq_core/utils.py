import re
import simplejson as json

from math import ceil

from django.db.models import Q
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404
from django.core.cache import cache, caches
from django.utils.functional import cached_property

from unidecode import unidecode
from raven.contrib.django.raven_compat.models import client as raven_client

from .models import CommerceHQStore, CommerceHQProduct, CommerceHQBoard, CommerceHQOrderTrack
from shopified_core import permissions
from shopified_core.utils import (
    safe_int,
    safe_float,
    safe_str,
    hash_url_filename,
    decode_params,
    http_exception_response,
    http_excption_status_code
)
from shopified_core.shipping_helper import (
    get_uk_province,
    fix_br_address,
    valide_aliexpress_province,
    support_other_in_province,
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
        store = get_object_or_404(stores, id=safe_int(request.GET.get('store')))

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


def duplicate_product(product, store=None):
    parent_product = CommerceHQProduct.objects.get(id=product.id)

    product.pk = None
    product.parent_product = parent_product
    product.source_id = 0

    if store is not None:
        product.store = store

    product_data = json.loads(product.data)

    if parent_product.source_id and parent_product.store:
        try:
            chq_product = parent_product.retrieve()

            product_data['variants'] = []

            for option in chq_product['options']:
                product_data['variants'].append({
                    'values': option['values'],
                    'title': option['title']
                })

            product_data['variants_sku'] = {}
            product_data['variants_images'] = {}
            variant_image_urls = []
            for variant in chq_product['variants']:
                if len(variant['sku'] or '') > 0:
                    titles = variant['variant']
                    values = variant['sku'].split(';')
                    if titles:
                        if values:
                            product_data['variants_sku'][titles[0]] = variant['sku']
                        else:
                            for k, v in titles:
                                if values.length > k:
                                    product_data['variants_sku'][titles[k]] = values[k]
                    else:
                        product_data['variants_sku'][variant['title']] = variant['sku']

                for image in variant['images']:
                    image_hash = hash_url_filename(image['path'])
                    product_data['variants_images'][image_hash] = variant['sku']
                    variant_image_urls.append(image['path'])

            product_data['images'] = [image['path'] for image in chq_product['images']] + variant_image_urls

            product.data = json.dumps(product_data)

        except Exception:
            raven_client.captureException(level='warning')

    product.save()

    for i in parent_product.get_suppliers():
        i.pk = None
        i.product = product
        i.store = product.store
        i.save()

        if i.is_default:
            product.set_default_supplier(i, commit=True)

    return product


def get_connected_options(product, split_factor):
    for attribute in product.parsed.get('options', []):
        if attribute['title'] == split_factor:
            return attribute


def get_non_connected_options(product, split_factor):
    for variant in product.parsed.get('variants', []):
        if variant['title'] == split_factor:
            return variant


def get_variant_options(product, split_factor):
    if product.source_id:
        return get_connected_options(product, split_factor)
    else:
        return get_non_connected_options(product, split_factor)


def split_product(product, split_factor, store=None):
    new_products = []
    options = get_variant_options(product, split_factor)

    parent_data = product.parsed
    title = parent_data.get('title', '')

    for value in options['values']:
        new_product = duplicate_product(product, product.store)
        new_data = new_product.parsed
        new_data['title'] = '{} ({})'.format(title, value)

        original_images = new_data.get('original_images', new_data.get('images', []))
        variant_images = new_data.get('variants_images', [])

        variants = new_data.get('variants', [])
        new_data['variants'] = [v for v in variants if not v['title'] == split_factor]

        hashes = [h for h, variant in list(variant_images.items()) if variant == value]
        new_data['images'] = [i for i in original_images if hash_url_filename(i) in hashes]

        new_product.update_data(new_data)
        new_product.save()
        new_products.append(new_product)

    return new_products


def get_chq_products_count(store):
    api_url = store.get_api_url('products')
    response = store.request.head(api_url)
    total_count = response.headers['X-Pagination-Total-Count']
    total = int(total_count)

    return total


def get_chq_products(store, page=1, limit=50, all_products=False, product_ids=None, expand='images,variants'):
    api_url = store.get_api_url('products')

    if not all_products:
        params = {'page': page, 'size': limit, 'expand': expand}

        if product_ids:
            for product_id in product_ids:
                response = store.request.get(api_url + '/' + str(product_id), params=params)
                product = response.json()
                yield product
        else:
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
        for page in range(1, pages + 1):
            response = get_chq_products(store=store, page=page, limit=limit, all_products=False)
            products = response.json()['items']
            for product in products:
                yield product


def get_chq_product(store, product_id):
    api_url = store.get_api_url('products')
    if store:
        params = {'expand': 'all'}
        response = store.request.get(api_url + '/' + str(product_id), params=params)

        return response.json()
    else:
        return None


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

            in_store = safe_int(request.GET.get('in'))
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


def chq_customer_address(order, aliexpress_fix=False, german_umlauts=False, fix_aliexpress_city=False, return_corrections=False):
    customer_address = {}
    shipping_address = order['shipping_address']

    for k in list(shipping_address.keys()):
        if shipping_address[k] and type(shipping_address[k]) is str:
            v = re.sub(' ?\xc2?[\xb0\xba] ?', r' ', shipping_address[k])
            if german_umlauts:
                v = re.sub('\u00e4', 'ae', v)
                v = re.sub('\u00c4', 'AE', v)
                v = re.sub('\u00d6', 'OE', v)
                v = re.sub('\u00fc', 'ue', v)
                v = re.sub('\u00dc', 'UE', v)
                v = re.sub('\u00f6', 'oe', v)

            customer_address[k] = unidecode(v)
        else:
            customer_address[k] = shipping_address[k]

    customer_address['address1'] = customer_address.get('street')
    customer_address['address2'] = customer_address.get('suite')
    customer_address['country_code'] = customer_address.get('country')
    customer_address['province_code'] = customer_address.get('state')

    customer_address['country'] = country_from_code(customer_address['country_code'])
    customer_address['province'] = province_from_code(customer_address['country_code'], customer_address['province_code'])

    customer_province = customer_address['province']
    if not customer_address.get('province'):
        if customer_address['country'].lower() == 'united kingdom' and customer_address['city']:
            province = get_uk_province(customer_address['city'])
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

    if customer_address['country_code'] == 'FR':
        if customer_address.get('zip'):
            customer_address['zip'] = re.sub(r'[\n\r\t\._ -]', '', customer_address['zip']).strip().rjust(5, '0')

    if customer_address['country_code'] == 'BR':
        customer_address = fix_br_address(customer_address)

    if customer_address['country_code'] == 'IL':
        if customer_address.get('zip'):
            customer_address['zip'] = re.sub(r'[\n\r\t\._ -]', '', customer_address['zip']).strip().rjust(7, '0')

    if customer_address['country_code'] == 'CA':
        if customer_address.get('zip'):
            customer_address['zip'] = re.sub(r'[\n\r\t ]', '', customer_address['zip']).upper().strip()

        if customer_address['province'] == 'Newfoundland':
            customer_address['province'] = 'Newfoundland and Labrador'

    if customer_address['country'].lower() == 'united kingdom':
        if customer_address.get('zip'):
            if not re.findall(r'^([0-9A-Za-z]{2,4}\s[0-9A-Za-z]{3})$', customer_address['zip']):
                customer_address['zip'] = re.sub(r'(.+)([0-9A-Za-z]{3})$', r'\1 \2', customer_address['zip'])

    if customer_address['country_code'] == 'MK':
        customer_address['country'] = 'Macedonia'

    if customer_address['country_code'] == 'PL':
        if customer_address.get('zip'):
            customer_address['zip'] = re.sub(r'[\n\r\t\._ -]', '', customer_address['zip'])

    customer_address['name'] = '{} {}'.format(customer_address['first_name'], customer_address['last_name'])
    # customer_address['name'] = utils.ensure_title(customer_address['name'])

    # if customer_address['company']:
    #     customer_address['name'] = '{} - {}'.format(customer_address['name'],
    #                                                 customer_address['company'])

    correction = {}
    if aliexpress_fix:
        valide, correction = valide_aliexpress_province(
            customer_address['country'],
            customer_address['province'],
            customer_address['city'],
            auto_correct=True)

        if not valide:
            if support_other_in_province(customer_address['country']):
                customer_address['province'] = 'Other'

                if customer_address['country'].lower() == 'united kingdom' and customer_address['city']:
                    province = get_uk_province(customer_address['city'])
                    if province:
                        customer_address['province'] = province

                if customer_province and customer_address['province'] == 'Other':
                    customer_address['city'] = '{}, {}'.format(customer_address['city'], customer_province)

            elif fix_aliexpress_city:
                city = safe_str(customer_address['city']).strip().strip(',')
                customer_address['city'] = 'Other'

                if not safe_str(customer_address['address2']).strip():
                    customer_address['address2'] = '{},'.format(city)
                else:
                    customer_address['address2'] = '{}, {},'.format(customer_address['address2'].strip().strip(','), city)

        elif correction:
            if 'province' in correction:
                customer_address['province'] = correction['province']

            if 'city' in correction:
                customer_address['city'] = correction['city']

    if return_corrections:
        return order, customer_address, correction
    else:
        return order, customer_address


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
    response = http_exception_response(e, json=True)
    if not response or http_excption_status_code(e) != 422:
        return 'Server Error'

    msg = []
    errors_list = response
    if type(errors_list) is not list:
        errors_list = [errors_list]

    for errors in errors_list:
        errors = errors.get('errors') or response.get('message')

        if not errors:
            msg.append('Server Error')
        elif isinstance(errors, str):
            msg.append(errors)
        else:
            for k, v in list(errors.items()):
                if type(v) is list:
                    error = ','.join(v)
                else:
                    error = v

                if k == 'base':
                    msg.append(error)
                else:
                    msg.append('{}: {}'.format(k, error))

    return ' | '.join(msg)


def store_shipping_carriers(store):
    rep = store.request.get(store.get_api_url('shipping-carriers'), params={'size': 100})
    if rep.ok:
        return rep.json()['items']
    else:
        carriers = [
            {1: 'USPS'}, {2: 'UPS'}, {3: 'FedEx'}, {4: 'LaserShip'},
            {5: 'DHL US'}, {6: 'DHL Global'}, {7: 'Canada Post'}
        ]

        return [{'id': list(c.keys()).pop(), 'title': list(c.values()).pop()} for c in carriers]


def set_orders_filter(user, filters, default=None):
    fields = ['sort', 'status', 'fulfillment', 'financial',
              'desc', 'connected', 'awaiting_order']

    for name, val in list(filters.items()):
        if name in fields:
            key = '_chq_orders_filter_{}'.format(name)
            user.set_config(key, val)


def get_orders_filter(request, name=None, default=None, checkbox=False):
    if name:
        key = '_chq_orders_filter_{}'.format(name)
        val = request.GET.get(name)

        if not val:
            val = request.user.get_config(key, default)

        return val
    else:
        filters = {}
        for name, val in list(request.user.profile.get_config().items()):
            if name.startswith('_chq_orders_filter_'):
                filters[name.replace('_chq_orders_filter_', '')] = val

        return filters


class CommerceHQOrdersPaginator(Paginator):
    store = None
    size = 20

    request = None

    query = None
    fulfillment = None
    financial = None
    sort = None
    query_field = 'id'

    _products = None
    _count = None
    _num_pages = None

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

    def set_filter(self, fulfillment, financial, sort, query=''):
        self.fulfillment = fulfillment
        self.financial = financial
        self.sort = sort

        self.query = decode_params(query or '')

        if '@' in self.query:
            self.query_field = 'email'
        else:
            track = CommerceHQOrderTrack.objects.filter(source_id=self.query).first()
            if track:
                self.query = str(track.order_id)

            self.query_field = 'id'
            self.query = re.sub(r'[^0-9]', '', self.query)

    def page(self, number):
        """
        Returns a Page object for the given 1-based page number.
        """

        number = self.validate_number(number)
        page_start = safe_int(self.request.GET.get('page_start'), 1)
        number += page_start - 1

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

        pages = list(range(max(1, self.current_page - 5), self.current_page))
        pages.extend(list(range(self.current_page, min(page_count + 1, self.current_page + 5))))

        if 1 not in pages:
            pages = [1, None] + pages

        if page_count not in pages:
            pages = pages + [None, page_count]

        return pages

    def _get_products(self):
        rep = self._orders_request()
        self._products = rep['items']

    @cached_property
    def count(self):
        """
        Returns the total number of objects, across all pages.
        """
        if self._count is None:
            rep = self._orders_count_request()
            self._count = rep['_meta']['totalCount']
            self._num_pages = rep['_meta']['pageCount']

        return self._count

    @cached_property
    def num_pages(self):
        if self._num_pages is None:
            rep = self._orders_count_request()
            self._count = rep['_meta']['totalCount']
            self._num_pages = rep['_meta']['pageCount']

        return self._num_pages

    def _request_filters(self):
        filters = {
            'status': self.fulfillment,
            'paid': self.financial,
        }

        filters[self.query_field] = self.query

        for k, v in list(filters.items()):
            if not v or v == 'any':
                del filters[k]
            elif ',' in v:
                filters[k] = v.split(',')

        for k, v in list(filters.items()):
            if type(filters[k]) is list:
                filters[k] = list(map((lambda x: safe_int(x)), filters[k]))
            elif k != 'email':
                filters[k] = safe_int(v, None)

            if not filters[k]:
                del filters[k]

        return filters

    def _orders_request(self):
        params = {
            'size': self.per_page,
            'page': getattr(self, 'current_page', 1),
            'sort': self.sort,
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


def get_shipping_carrier(shipping_carrier_name, store, carrier_id=None):
    cache_key = 'chq_shipping_carriers_{}_{}'.format(store.id, shipping_carrier_name)

    shipping_carriers = cache.get(cache_key)
    if shipping_carriers is not None:
        return shipping_carriers

    shipping_carriers_map = {}
    for i in store_shipping_carriers(store):
        # Shipping carrier id can be defined in user config
        if carrier_id and safe_int(carrier_id) == i['id'] and not i.get('is_deleted', False):
            return i
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

                    if item['quantity'] == 0:
                        store.request.delete(url=store.get_api_url('orders', order['id'], 'fulfilments', fulfilment.get('id')))
                        caches['orders'].delete('chq_fulfilments_{}_{}_{}'.format(*args))

                    if 'chq_quantity_{}_{}_{}'.format(*args) not in cache_data and item['quantity']:
                        cache_data['chq_quantity_{}_{}_{}'.format(*args)] = item['quantity']

    caches['orders'].set_many(cache_data, timeout=604800)

    return list(cache_data.keys())


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

    custom_tracking_carrier = user_config.get('chq_custom_tracking', {})
    custom_tracking_carrier_id = None
    if custom_tracking_carrier:
        custom_tracking_carrier_id = custom_tracking_carrier.get(str(order_track.store_id))

    shipping_carrier = get_shipping_carrier(shipping_carrier_name, order_track.store, carrier_id=custom_tracking_carrier_id)

    if fulfilment_id is None:
        store = order_track.store
        api_data = {
            "items": [{
                "id": order_track.line_id,
                "quantity": caches['orders'].get('chq_quantity_{}_{}_{}'.format(store.id, order_track.order_id, order_track.line_id)) or 1,
            }]
        }

        rep = store.request.post(
            url=store.get_api_url('orders', order_track.order_id, 'fulfilments'),
            json=api_data
        )

        try:
            rep.raise_for_status()

            for fulfilment in rep.json()['fulfilments']:
                for item in fulfilment['items']:
                    caches['orders'].set('chq_fulfilments_{}_{}_{}'.format(store.id, order_track.order_id, item['id']),
                                         fulfilment['id'], timeout=604800)

            fulfilment_id = caches['orders'].get('chq_fulfilments_{store_id}_{order_id}_{line_id}'.format(**kwargs))

        except Exception as e:
            if not rep.ok and 'Warehouse ID' in rep.text:
                raise

            raven_client.captureException(level='warning', extra=http_exception_response(e))

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


def fix_order_variants(store, order, product):
    product_key = 'fix_product_{}_{}'.format(store.id, product.get_chq_id())
    chq_product = cache.get(product_key)

    if chq_product is None:
        chq_product = get_chq_product(store, product.get_chq_id())
        cache.set(product_key, chq_product)

    def normalize_name(n):
        return n.lower().replace(' and ', '').replace(' or ', '').replace(' ', '')

    def get_variant(product, variant_id=None, variant_list=None):
        for v in product['variants']:
            if variant_id and v['id'] == int(variant_id):
                return v
            elif variant_list and all([l in v['variant'] for l in variant_list]) and len(v['variant']) == len(variant_list):
                return v

        return None

    def set_real_variant(product, deleted_id, real_id):
        config = product.get_config()
        mapping = config.get('real_variant_map', {})
        mapping[str(deleted_id)] = int(real_id)

        config['real_variant_map'] = mapping

        product.config = json.dumps(config, indent=4)
        product.save()

    for line in order['items']:
        if line['data']['product_id'] != product.get_chq_id() or not line['data']['is_multi']:
            continue

        if get_variant(chq_product, variant_id=line['data']['variant']['id']) is None:
            real_id = product.get_real_variant_id(line['data']['variant']['id'])
            match = get_variant(chq_product, variant_list=line['data']['variant']['variant'])
            if match:
                if real_id != match['id']:
                    set_real_variant(product, line['data']['variant']['id'], match['id'])


def set_chq_order_note(store, order_id, note):
    api_url = store.get_api_url('orders', order_id)
    r = store.request.patch(api_url, {'notes': note})
    r.raise_for_status()

    return r.json().get('id')


def get_chq_order(store, order_id):
    order_url = store.get_api_url('orders', order_id, api=True)
    rep = store.request.get(url=order_url)
    rep.raise_for_status()

    return rep.json()


def get_chq_order_note(store, order_id):
    order = get_chq_order(store, order_id)
    return order.get('notes')


class CHQOrderUpdater:

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
            current_note = ''
            if add:
                order = get_chq_order(self.store, self.order_id)
                current_note = order.get('notes', '') or ''
            if current_note:
                new_note = '{}\n{}'.format(current_note, new_note).strip()[:5000]
            else:
                new_note = '{}'.format(new_note).strip()[:5000]
            set_chq_order_note(self.store, self.order_id, new_note)

    def delay_save(self, countdown=None):
        from commercehq_core.tasks import order_save_changes

        order_save_changes.apply_async(
            args=[self.toJSON()],
            countdown=countdown
        )

    def reset(self, what):
        order_data = {}

        if 'notes' in what:
            order_data['notes'] = ''

        if len(list(order_data.keys())) > 1:
            order_url = self.store.get_api_url('orders', self.order_id, api=True)
            rep = self.store.request.patch(order_url, order_data)

            rep.raise_for_status()

    def toJSON(self):
        return json.dumps({
            "notes": self.notes,
            "order": self.order_id,
            "store": self.store.id,
        }, sort_keys=True, indent=4)

    def fromJSON(self, data):
        if type(data) is not dict:
            data = json.loads(data)

        self.store = CommerceHQStore.objects.get(id=data.get("store"))
        self.order_id = data.get("order")

        self.notes = data.get("notes")
