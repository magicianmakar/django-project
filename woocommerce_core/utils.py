import re
import json
import itertools
import urllib
import arrow
import requests

from math import ceil
from measurement.measures import Weight
from decimal import Decimal, ROUND_HALF_UP
from unidecode import unidecode

from django.db.models import Q
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.core.exceptions import PermissionDenied
from django.core.cache import cache, caches
from django.utils import timezone

from shopified_core import permissions
from shopified_core.paginators import SimplePaginator
from shopified_core.utils import safeInt, safeFloat, hash_url_filename, decode_params, http_exception_response
from shopified_core.shipping_helper import (
    load_uk_provincess,
    country_from_code,
    province_from_code
)

import leadgalaxy.utils as leadgalaxy_utils

from .models import WooProduct, WooStore, WooBoard


def filter_products(res, fdata):
    if fdata.get('title'):
        title = decode_params(fdata.get('title'))
        res = res.filter(title__icontains=title)

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


def woocommerce_products(request, post_per_page=25, sort=None, board=None, store='n'):
    store = request.GET.get('store', store)
    sort = request.GET.get('sort')

    user_stores = request.user.profile.get_woo_stores(flat=True)
    res = WooProduct.objects.select_related('store') \
                            .filter(user=request.user.models_user) \
                            .filter(Q(store__in=user_stores) | Q(store=None))

    if store:
        if store == 'c':  # connected
            res = res.exclude(source_id=0)
        elif store == 'n':  # non-connected
            res = res.filter(source_id=0)

            in_store = safeInt(request.GET.get('in'))
            if in_store:
                in_store = get_object_or_404(WooStore, id=in_store)
                res = res.filter(store=in_store)

                permissions.user_can_view(request.user, in_store)
        else:
            store = get_object_or_404(WooStore, id=store)
            res = res.filter(source_id__gt=0, store=store)

            permissions.user_can_view(request.user, store)

    if board:
        res = res.filter(wooboard=board)
        permissions.user_can_view(request.user, get_object_or_404(WooBoard, id=board))

    res = filter_products(res, request.GET)

    if sort:
        if re.match(r'^-?(title|price)$', sort):
            res = res.order_by(sort)

    return res


def format_woo_errors(e):
    if isinstance(e, requests.exceptions.ConnectionError) or \
            isinstance(e, requests.exceptions.ConnectTimeout) or \
            isinstance(e, requests.exceptions.ReadTimeout):
        return 'Error when connecting to your WooCommerce Store'
    else:
        return http_exception_response(e, json=True).get('message', 'Server Error')


def update_product_api_data(api_data, data, store):
    api_data['name'] = data['title']
    api_data['status'] = 'publish' if data['published'] else 'draft'
    api_data['price'] = str(data['price'])
    api_data['regular_price'] = str(data['compare_at_price'])
    api_data['description'] = data.get('description')

    try:
        api_data['weight'] = str(match_weight(safeFloat(data['weight']), data['weight_unit'], store))
    except:
        pass

    return api_data


def add_product_images_to_api_data(api_data, data):
    api_data['images'] = []
    for position, src in enumerate(data.get('images', [])):
        api_data['images'].append({'src': src, 'name': src, 'position': position})

    return api_data


def add_product_attributes_to_api_data(api_data, data):
    variants = data.get('variants', [])
    if variants:
        api_data['type'] = 'variable'
        api_data['attributes'] = []
        for num, variant in enumerate(variants):
            name, options = variant.get('title'), variant.get('values', [])
            attribute = {'position': num + 1, 'name': name, 'options': options, 'variation': True}
            api_data['attributes'].append(attribute)

    return api_data


def get_image_id_by_hash(product_data):
    image_id_by_hash = {}
    for image in product_data.get('images', []):
        hash_ = hash_url_filename(image['name'])
        image_id_by_hash[hash_] = image['id']

    return image_id_by_hash


def create_variants_api_data(data, image_id_by_hash):
    variants = data.get('variants', [])
    variants_images = data.get('variants_images', {}).items()
    variant_list = []

    titles, values = [], []
    for variant in variants:
        titles.append(variant.get('title', ''))
        values.append(variant.get('values', []))

    # Iterates through all possible variants e.g. [(RED, LARGE), (RED, SMALL)]
    for product in itertools.product(*values):
        api_data = {'attributes': []}
        descriptions = []
        for name, option in itertools.izip(titles, product):
            descriptions.append('{}: {}'.format(name, option))
            api_data['attributes'].append({'name': name, 'option': option})
            if 'image' not in api_data:
                for image_hash, variant_option in variants_images:
                    if image_hash in image_id_by_hash and variant_option == option:
                        api_data['image'] = {'id': image_id_by_hash[image_hash]}

        api_data['description'] = ' | '.join(descriptions)

        if data.get('compare_at_price'):
            api_data['regular_price'] = str(data['compare_at_price'])
            api_data['sale_price'] = str(data['price'])
        else:
            api_data['regular_price'] = str(data['price'])

        variant_list.append(api_data)

    return variant_list


def add_store_tags_to_api_data(api_data, store, tags):
    if not tags:
        api_data['tags'] = []
    else:
        tags = tags.split(',')
        create = [{'name': tag.strip()} for tag in tags if tag]

        # Creates tags that haven't been created yet. Returns an error if tag exists.
        r = store.wcapi.post('products/tags/batch', {'create': create})
        r.raise_for_status()

        store_tags = r.json()['create']
        tag_ids = []
        for store_tag in store_tags:
            if 'id' in store_tag:
                tag_ids.append(store_tag['id'])
            if 'error' in store_tag:
                if store_tag['error'].get('code', '') == 'term_exists':
                    tag_ids.append(store_tag['error']['data']['resource_id'])

        api_data['tags'] = [{'id': tag_id} for tag_id in tag_ids]

    return api_data


def update_product_images_api_data(api_data, data):
    images = []
    data_images = data.get('images', [])
    product_images = api_data.get('images', [])
    product_image_srcs = [img['src'] for img in product_images]

    for product_image in product_images:
        if product_image['id'] == 0:
            continue  # Skips the placeholder image to avoid error
        if product_image['src'] in data_images:
            images.append({'id': product_image['id']})  # Keeps the current image

    for data_image in data_images:
        if data_image not in product_image_srcs:
            images.append({'src': data_image})  # Adds the new image

    if images:
        images[0]['position'] = 0  # Sets as featured image

    api_data['images'] = images if images else ''  # Deletes all images if empty

    return api_data


def update_variants_api_data(data):
    variants = []
    for item in data:
        variant = {'id': item['id'], 'sku': item['sku']}

        if item.get('compare_at_price'):
            variant['sale_price'] = str(item['price'])
            variant['regular_price'] = str(item['compare_at_price'])
        else:
            variant['regular_price'] = str(item['price'])

        variants.append(variant)

    return variants


def disconnect_data(product):
    data = product.parsed
    data.pop('id')
    data.pop('published')
    data.pop('product_type')
    data['status'] = 'draft'
    data['variants'] = []
    data['images'] = data.pop('original_images', data['images'])

    for attribute in data.pop('attributes', []):
        title, values = attribute['name'], attribute['options']
        data['variants'].append({'title': title, 'values': values})

    product.data = json.dumps(data)

    return product


@transaction.atomic
def duplicate_product(product, store=None):
    parent_product = WooProduct.objects.get(id=product.id)
    product.pk = None
    product.parent_product = parent_product
    product.source_id = 0
    product.store = store
    product = disconnect_data(product) if product.parsed.get('id') else product
    product.save()

    for supplier in parent_product.woosupplier_set.all():
        supplier.pk = None
        supplier.product = product
        supplier.store = product.store
        supplier.save()

        if supplier.is_default:
            product.set_default_supplier(supplier, commit=True)

    return product


def match_weight(weight, unit, store):
    r = store.wcapi.get('settings/products/woocommerce_weight_unit')
    r.raise_for_status()
    store_unit = r.json()['value']
    store_unit = 'lb' if store_unit == 'lbs' else store_unit
    product_weight = Weight(**{unit: weight})
    weight_decimal = Decimal(str(weight))

    if not unit == store_unit:
        converted = str(getattr(product_weight, store_unit))
        return Decimal(converted).quantize(weight_decimal, rounding=ROUND_HALF_UP)

    return weight_decimal


def get_connected_options(product, split_factor):
    for attribute in product.parsed.get('attributes', []):
        if attribute['name'] == split_factor:
            return attribute['options']


def get_non_connected_options(product, split_factor):
    for variant in product.parsed.get('variants', []):
        if variant['title'] == split_factor:
            return variant['values']


def get_variant_options(product, split_factor):
    if product.source_id:
        return get_connected_options(product, split_factor)
    else:
        return get_non_connected_options(product, split_factor)


def split_product(product, split_factor, store=None):
    new_products = []
    options = get_variant_options(product, split_factor)
    parent_data = product.parsed
    original_images = parent_data.get('original_images', parent_data.get('images', []))
    variant_images = parent_data.get('variants_images', [])
    title = parent_data.get('title', '')

    for option in options:
        new_product = duplicate_product(product, product.store)
        new_data = {}
        new_data['title'] = u'{} ({})'.format(title, option)

        variants = new_product.parsed.get('variants', [])
        new_data['variants'] = [v for v in variants if not v['title'] == split_factor]

        hashes = [h for h, variant in variant_images.items() if variant == option]
        new_data['images'] = [i for i in original_images if hash_url_filename(i) in hashes]

        new_product.update_data(new_data)
        new_product.save()
        new_products.append(new_product)

    return new_products


def get_store_from_request(request):
    store = None
    stores = request.user.profile.get_woo_stores()

    if request.GET.get('shop'):
        try:
            store = stores.get(shop=request.GET.get('shop'))
        except (WooStore.DoesNotExist, WooStore.MultipleObjectsReturned):
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

        except (PermissionDenied, WooStore.DoesNotExist):
            store = None

    if not store:
        store = stores.first()

    return store


def store_shipping_carriers(store):
    carriers = [
        {1: 'USPS'}, {2: 'UPS'}, {3: 'FedEx'}, {4: 'LaserShip'},
        {5: 'DHL US'}, {6: 'DHL Global'}, {7: 'Canada Post'},
        {8: 'Custom Provider'},
    ]

    return map(lambda c: {'id': c.keys().pop(), 'title': c.values().pop()}, carriers)


def get_shipping_carrier_name(store, carrier_id):
    shipping_carriers = store_shipping_carriers(store)
    for carrier in shipping_carriers:
        if carrier['id'] == carrier_id:
            return carrier['title']


def get_order_line_fulfillment_status(order_line):
    for meta in order_line.get('meta_data', []):
        if meta['key'] == 'Fulfillment Status':
            return meta['value']


def has_order_line_been_fulfilled(order_line):
    return get_order_line_fulfillment_status(order_line) == 'Fulfilled'


def cache_fulfillment_data(order_tracks, orders_max=None):
    """
    Caches order data of given `WooOrderTrack` instances
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
        include = ','.join(str(order_id) for order_id in order_ids)

        for chunk_include in [include[x:x + 20] for x in xrange(0, len(include), 20)]:
            page = 1
            while page:
                params = {'page': page, 'per_page': 100, 'include': chunk_include}
                query_string = urllib.urlencode(params)
                r = store.wcapi.get('orders?{}'.format(query_string))
                r.raise_for_status()

                orders = r.json()

                for order in orders:
                    country = order['shipping']['country'] or order['billing']['country']
                    cache_data['woo_auto_country_{}_{}'.format(store.id, order['id'])] = country

                    for item in order.get('line_items', []):
                        args = store.id, order['id'], item['id']
                        cache_key = 'woo_auto_fulfilled_order_{}_{}_{}'.format(*args)
                        cache_data[cache_key] = has_order_line_been_fulfilled(item)

                has_next = 'rel="next"' in r.headers.get('link', '')
                page = page + 1 if has_next else 0

    cache.set_many(cache_data, timeout=3600)

    return cache_data.keys()


def cached_order_line_fulfillment_status(order_track):
    args = order_track.store.id, order_track.order_id, order_track.line_id

    return cache.get('woo_auto_fulfilled_order_{}_{}_{}'.format(*args))


def order_track_fulfillment(order_track, user_config=None):
    user_config = {} if user_config is None else user_config
    tracking_number = order_track.source_tracking

    kwargs = {
        'store_id': order_track.store_id,
        'order_id': order_track.order_id,
        'line_id': order_track.line_id
    }

    # Keys are set by `woocommerce_core.utils.cache_fulfillment_data`
    country = cache.get('woo_auto_country_{store_id}_{order_id}'.format(**kwargs))

    shipping_carrier_name = leadgalaxy_utils.shipping_carrier(tracking_number)
    if country and country == 'US':
        if leadgalaxy_utils.is_chinese_carrier(tracking_number) or leadgalaxy_utils.shipping_carrier(tracking_number) == 'USPS':
            shipping_carrier_name = 'USPS'

    shipping_carrier_name = 'AfterShip' if not shipping_carrier_name else shipping_carrier_name
    date_shipped = arrow.get(timezone.now()).format('MM/DD/YYYY')

    meta_data = get_fulfillment_meta(
        shipping_carrier_name,
        tracking_number,
        order_track.get_tracking_link(),
        date_shipped
    )

    data = {
        'line_items': [{
            'id': order_track.line_id,
            'product_id': order_track.product_id,
            'meta_data': meta_data
        }],
        'status': 'processing'
    }

    return data


def order_id_from_name(store, order_name, default=None):
    ''' Get Order ID from Order Name '''

    order_rx = store.user.get_config('order_number', {}).get(str(store.id), '[0-9]+')
    order_number = re.findall(order_rx, order_name)
    if not order_number:
        return default

    r = store.wcapi.get('orders?{}'.format(urllib.urlencode({'search': order_name})))

    if r.ok:
        orders = r.json()

        if len(orders):
            return orders.pop()['id']

    return default


def get_tracking_products(store, tracker_orders, per_page=50):
    ids = []
    for i in tracker_orders:
        ids.append(str(i.product_id))

    if not len(ids):
        return tracker_orders

    params = {'include': ','.join(ids), 'per_page': per_page}
    r = store.wcapi.get(u'products?{}'.format(urllib.urlencode(params)))
    r.raise_for_status()

    products = {}
    for product in r.json():
        products[product['id']] = product

    new_tracker_orders = []
    for tracked in tracker_orders:
        tracked.product = product = products.get(tracked.product_id)
        if product:
            image = next(iter(product['images']), {})
            tracked.line['image'] = image.get('src')
            variation_id = tracked.line.get('variation_id')
            if variation_id:
                path = 'products/{}/variations/{}'.format(product['id'], variation_id)
                r = store.wcapi.get(path)
                r.raise_for_status()
                tracked.variation = r.json()
                variation_image = tracked.variation.get('image', {}).get('src')
                if 'placeholder.png' not in variation_image:
                    tracked.line['image'] = variation_image

        new_tracker_orders.append(tracked)

    return new_tracker_orders


def get_tracking_orders(store, tracker_orders, per_page=50):
    ids = []
    for i in tracker_orders:
        ids.append(str(i.order_id))

    if not len(ids):
        return tracker_orders

    params = {'include': ','.join(ids), 'per_page': per_page}
    r = store.wcapi.get('orders?{}'.format(urllib.urlencode(params)))
    r.raise_for_status()

    orders = {}
    lines = {}

    for order in r.json():
        orders[order['id']] = order
        for line in order['line_items']:
            line['image'] = line.get('image', {}).get('src', '')
            lines['{}-{}'.format(order['id'], line['id'])] = line

    new_tracker_orders = []
    for tracked in tracker_orders:
        tracked.order = orders.get(tracked.order_id)
        tracked.line = lines.get('{}-{}'.format(tracked.order_id, tracked.line_id))

        if tracked.line:
            fulfillment_status = (get_order_line_fulfillment_status(tracked.line) or '').lower()
            tracked.line['fulfillment_status'] = fulfillment_status

            if tracked.woocommerce_status != fulfillment_status:
                tracked.woocommerce_status = fulfillment_status
                tracked.save()

        new_tracker_orders.append(tracked)

    return new_tracker_orders


def smart_board_by_board(user, board):
    for product in user.wooproduct_set.all():
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


def get_woo_products_count(store):
    return WooListQuery(store, 'products').count()


def get_woo_products(store, page=1, limit=50, all_products=False):
    if not all_products:
        path = 'products?{}'.format(urllib.urlencode({'page': page, 'per_page': limit}))
        r = store.wcapi.get(path)
        r.raise_for_status()
        for product in r.json():
            yield product
    else:
        limit = 100
        count = get_woo_products_count(store)

        if not count:
            return

        pages = int(ceil(count / float(limit)))
        for page in xrange(1, pages + 1):
            products = get_woo_products(store=store, page=page, limit=limit, all_products=False)
            for product in products:
                yield product


def woo_customer_address(order):
    customer_address = {}
    shipping_address = order['shipping'] if any(order['shipping'].values()) else order['billing']

    for k in shipping_address.keys():
        if shipping_address[k] and type(shipping_address[k]) is unicode:
            customer_address[k] = unidecode(shipping_address[k])
        else:
            customer_address[k] = shipping_address[k]

    customer_address['address1'] = customer_address.get('address_1')
    customer_address['address2'] = customer_address.get('address_2')
    customer_address['country_code'] = customer_address.get('country')
    customer_address['province_code'] = customer_address.get('state')
    customer_address['zip'] = customer_address.get('postcode')

    customer_address['country'] = country_from_code(customer_address['country_code'], '')
    customer_address['province'] = province_from_code(customer_address['country_code'], customer_address['province_code'])

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
            if not re.findall('^([0-9A-Za-z]{2,4}\s[0-9A-Za-z]{3})$', customer_address['zip']):
                customer_address['zip'] = re.sub(r'(.+)([0-9A-Za-z]{3})$', r'\1 \2', customer_address['zip'])

    customer_address['name'] = u'{} {}'.format(customer_address['first_name'], customer_address['last_name']).strip()

    return customer_address


def order_data_cache(*args, **kwargs):
    order_key = '_'.join([str(i) for i in args])

    if not order_key.startswith('woo_order_'):
        order_key = 'woo_order_{}'.format(order_key)

    if '*' in order_key:
        data = caches['orders'].get_many(caches['orders'].keys(order_key))
    else:
        data = caches['orders'].get(order_key)

    return data


def get_latest_order_note(store, order_id):
    r = store.wcapi.get('orders/{}/notes'.format(order_id))

    if r.ok:
        notes = r.json()
        return next(iter(notes), {}).get('note', '')

    return ''


def add_woo_order_note(store, order_id, note):
    r = store.wcapi.post('orders/{}/notes'.format(order_id), {'note': note})
    r.raise_for_status()

    return r.json()


def get_order_track_product_id(store, order_id, line_id):
    order_key = 'woo_order_{}_{}_{}'.format(store.id, order_id, line_id)
    order = order_data_cache(order_key)
    if order:
        return order['product_source_id']

    r = store.wcapi.get('orders/{}'.format(order_id))
    if r.ok:
        order = r.json()
        for line_item in order['line_items']:
            if line_item['id'] == line_id:
                return line_item['product_id']


def get_product_data(store, product_ids=None):
    product_data_by_product_id = {}
    page = 1
    while page:
        params = {'page': page, 'per_page': 100}
        if product_ids is not None:
            product_ids = [str(product_id) for product_id in product_ids]
            params['include'] = ','.join(product_ids)

        r = store.wcapi.get(u'products?{}'.format(urllib.urlencode(params)))
        r.raise_for_status()
        products = r.json()

        for product in products:
            product_data_by_product_id[product['id']] = product

        has_next = 'rel="next"' in r.headers.get('link', '')
        page = page + 1 if has_next else 0

    return product_data_by_product_id


def get_unfulfilled_items(order):
    return [item for item in order.get('line_items') if not has_order_line_been_fulfilled(item)]


def get_fulfillment_meta(shipping_carrier_name, tracking_number, tracking_link, date_shipped):
    return [
        {'key': 'Fulfillment Status', 'value': 'Fulfilled'},
        {'key': 'Provider', 'value': shipping_carrier_name},
        {'key': 'Tracking Number', 'value': tracking_number},
        {'key': 'Tracking Link', 'value': tracking_link},
        {'key': 'Date Shipped', 'value': date_shipped},
    ]


def update_order_status(store, order_id, status, tries=3):
    while tries > 0:
        tries -= 1
        r = store.wcapi.put('orders/{}'.format(order_id), {'status': status})
        if r.ok:
            break


class WooListQuery(object):
    def __init__(self, store, endpoint, params=None):
        self._store = store
        self._endpoint = endpoint
        self._params = {} if params is None else params
        self._response = None

    @property
    def response(self):
        return self._response if self.has_response else self.get_response()

    @property
    def has_response(self):
        return self._response is not None

    def get_response(self):
        params = urllib.urlencode(self._params)
        endpoint = '{}?{}'.format(self._endpoint, params)
        self._response = self._store.wcapi.get(endpoint)
        self._response.raise_for_status()

        return self._response

    def items(self):
        return self.response.json()

    def count(self):
        return int(self.response.headers['X-WP-Total'])

    def update_params(self, update):
        self._response = None
        self._params.update(update)

        return self


class WooListPaginator(SimplePaginator):
    def page(self, number):
        number = self.validate_number(number)
        self.current_page = number
        params = {'page': number, 'per_page': self.per_page}
        # `self.object_list` is a `WooListQuery` instance
        items = self.object_list.update_params(params).items()

        return self._get_page(items, number, self)


class WooOrderUpdater:

    def __init__(self, store=None, order_id=None):
        self.store = store
        self.order_id = order_id

        self.notes = []

    def add_note(self, n):
        self.notes.append(n)

    def mark_as_ordered_note(self, line_id, source_id):
        note = 'Aliexpress Order ID: {0}\n' \
               'http://trade.aliexpress.com/order_detail.htm?orderId={0}'.format(source_id)

        if line_id:
            note = u'{}\nOrder Line: #{}'.format(note, line_id)

        self.add_note(note)

    def save_changes(self, add=True):
        with cache.lock('updater_lock_{}_{}'.format(self.store.id, self.order_id), timeout=15):
            self._do_save_changes(add=add)

    def _do_save_changes(self, add=True):
        if self.notes:
            new_note = u'\n'.join(self.notes)
            add_woo_order_note(self.store, self.order_id, new_note)

    def delay_save(self, countdown=None):
        from woocommerce_core.tasks import order_save_changes

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

        self.store = WooStore.objects.get(id=data.get("store"))
        self.order_id = data.get("order")

        self.notes = data.get("notes")
