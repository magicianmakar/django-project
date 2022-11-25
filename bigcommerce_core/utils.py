import re
import json
import itertools
import requests
import copy

from unidecode import unidecode
from math import ceil
from collections import Counter
from base64 import b64encode

from lib.exceptions import capture_message

from django.db.models import Q
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.core.exceptions import PermissionDenied
from django.core.cache import cache, caches

from shopified_core import permissions
from shopified_core.paginators import SimplePaginator
from shopified_core.utils import (
    safe_int,
    safe_float,
    safe_str,
    hash_url_filename,
    products_filter,
    http_exception_response,
    get_top_most_commons,
    get_first_valid_option,
    order_data_cache,
    normalize_product_title
)
from shopified_core.shipping_helper import (
    get_uk_province,
    fix_br_address,
    valide_aliexpress_province,
    country_from_code,
    province_from_code,
    support_other_in_province
)

import leadgalaxy.utils as leadgalaxy_utils
from supplements.utils import supplement_customer_address

from .models import BigCommerceStore, BigCommerceProduct, BigCommerceBoard


def bigcommerce_products(request, post_per_page=25, sort=None, board=None, store='n'):
    store = request.GET.get('store', store)
    sort = request.GET.get('sort')

    user_stores = request.user.profile.get_bigcommerce_stores(flat=True)
    res = BigCommerceProduct.objects.select_related('store') \
                            .filter(user=request.user.models_user) \
                            .filter(Q(store__in=user_stores) | Q(store=None))

    if store:
        if store == 'c':  # connected
            res = res.exclude(source_id=0)
        elif store == 'n':  # non-connected
            res = res.filter(source_id=0)

            in_store = safe_int(request.GET.get('in'))
            if in_store:
                in_store = get_object_or_404(BigCommerceStore, id=in_store)
                res = res.filter(store=in_store)

                permissions.user_can_view(request.user, in_store)
        else:
            store = get_object_or_404(BigCommerceStore, id=store)
            res = res.filter(source_id__gt=0, store=store)

            permissions.user_can_view(request.user, store)

    if board:
        res = res.filter(bigcommerceboard=board)
        permissions.user_can_view(request.user, get_object_or_404(BigCommerceBoard, id=board))

    res = products_filter(res, request.GET)

    if sort:
        if re.match(r'^-?(title|price)$', sort):
            res = res.order_by(sort)

    return res


def format_bigcommerce_errors(e):
    if isinstance(e, requests.exceptions.ConnectionError) or \
            isinstance(e, requests.exceptions.ConnectTimeout) or \
            isinstance(e, requests.exceptions.ReadTimeout):
        return 'Error when connecting to your BigCommerce Store'
    else:
        return http_exception_response(e, json=True).get('title', 'Server Error')


def update_product_api_data(api_data, data):
    api_data['name'] = normalize_product_title(data['title'])
    api_data['type'] = 'physical'
    api_data['is_visible'] = True if data['published'] else False
    api_data['description'] = data.get('description')

    api_data['price'] = safe_float(data['price'])
    compare_at_price = safe_float(data['compare_at_price'])
    if compare_at_price:
        api_data['sale_price'] = api_data['price']
        api_data['price'] = compare_at_price

    try:
        weight = data.get('weight', 1.0)
        if data['weight_unit'] == 'g':
            weight = safe_float(weight, 0.0) / 1000.0
        elif data['weight_unit'] == 'lb':
            weight = safe_float(weight, 0.0) * 0.45359237
        elif data['weight_unit'] == 'oz':
            weight = safe_float(weight, 0.0) * 0.0283495
        else:
            weight = safe_float(weight, 0.0)
        api_data['weight'] = '{:.02f}'.format(weight)
    except:
        pass

    return api_data


def add_product_images_to_api_data(api_data, data, from_helper=False):
    api_data['images'] = []
    is_thumbnail = True
    for src in data.get('images', []):
        if from_helper:
            src = f"https://shopified-helper-app.herokuapp.com/api/ali/get-image/image.jpg?url={b64encode(src.encode('utf-8')).decode('utf-8')}"
        api_data['images'].append({'image_url': src, 'is_thumbnail': is_thumbnail})
        is_thumbnail = False

    return api_data


def get_image_url_by_hash(data):
    image_url_by_hash = {}
    for image in data.get('images', []):
        hash_ = hash_url_filename(image)
        image_url_by_hash[hash_] = image

    return image_url_by_hash


def create_variants_api_data(product_id, data, image_url_by_hash):
    variants = data.get('variants', [])
    variants_info = data.get('variants_info', {})
    variants_images = list(data.get('variants_images', {}).items())
    variant_list = []

    titles, values = [], []
    for variant in variants:
        titles.append(variant.get('title', ''))
        values.append(variant.get('values', []))

    # Iterates through all possible variants e.g. [(RED, LARGE), (RED, SMALL)]
    for product in itertools.product(*values):
        api_data = {'option_values': []}
        descriptions = [str(product_id)]
        options = []
        for name, option in zip(titles, product):
            options.append(option)
            descriptions.append('{}: {}'.format(name, option))
            api_data['option_values'].append({'option_display_name': name, 'label': option})
            if 'image' not in api_data:
                for image_hash, variant_option in variants_images:
                    if image_hash in image_url_by_hash and variant_option == option:
                        api_data['image_url'] = image_url_by_hash[image_hash]

        api_data['sku'] = ' | '.join(descriptions)

        if data.get('compare_at_price'):
            api_data['price'] = str(data['compare_at_price'])
            api_data['sale_price'] = str(data['price'])
        else:
            api_data['price'] = str(data['price'])

        variant_name = ' / '.join(options)
        variant = variants_info.get(variant_name, {})
        if variant.get('compare_at'):
            api_data['price'] = str(variant['compare_at'])
            api_data['sale_price'] = str(variant['price'])
        elif variant.get('price'):
            api_data['price'] = str(variant['price'])

        variant_list.append(api_data)

    return variant_list


def update_product_images_api_data(api_data, data):
    images = []
    data_images = data.get('images', [])
    product_images = api_data.get('images', [])
    product_image_srcs = [img['url_standard'] for img in product_images]

    for data_image in data_images:
        if data_image not in product_image_srcs:
            images.append({'image_url': data_image})  # Adds the new image

    api_data['images'] = images

    return api_data


def get_deleted_product_images(api_data, data):
    data_images = data.get('images', [])
    api_images = api_data.get('images', [])
    return [img['id'] for img in api_images if img['url_standard'] not in data_images]


def update_variants_api_data(api_data, data):
    variants = []
    for idx, item in enumerate(data):
        variant = api_data[idx]

        if item.get('compare_at_price'):
            variant['sale_price'] = safe_float(item['price'])
            variant['price'] = safe_float(item['compare_at_price'])
        else:
            variant['sale_price'] = 0
            variant['price'] = safe_float(item['price'])

        variants.append(variant)

    return variants


def map_images(product, product_data):
    variants_images = {}
    image_options_map = {}
    images = product_data.get('images', [])[:]
    images = [img['url_standard'] for img in images]
    variants = product_data.get('variants', [])

    for variant in variants:
        src = variant.get('image_url')
        hash_src = hash_url_filename(src)
        variant_options = [option['label'] for option in variant['option_values']]
        image_options_map.setdefault(hash_src, variant_options).extend(variant_options)
        options = image_options_map.get(hash_src, [])
        most_commons = Counter(options).most_common()
        if most_commons:
            top_most_commons = get_top_most_commons(most_commons)
            if len(top_most_commons) == 1:
                # Sets the image to its most popular option
                option, count = top_most_commons[0]
                variants_images[hash_src] = option
            else:
                # In case of a tie, assigns the first valid option
                valid_options = [option['label'] for option in product_data['options'][0]['option_values']]
                variants_images[hash_src] = get_first_valid_option(top_most_commons, valid_options)

        if src not in images:
            images.append(src)

    product.update_data({'images': images})
    product.update_data({'variants_images': variants_images})


def map_variants(product, product_data):
    variants = []

    for option in product_data.get('options', []):
        title, values = option['display_name'], [value['label'] for value in option['option_values']]
        variants.append({'title': title, 'values': values})

    product.update_data({'variants': variants})


def disconnect_data(product):
    product_data = product.retrieve()
    map_images(product, product_data)
    map_variants(product, product_data)
    data = product.parsed
    data.pop('id')
    product.data = json.dumps(data)

    return product


@transaction.atomic
def duplicate_product(product, store=None):
    parent_product = BigCommerceProduct.objects.get(id=product.id)
    product = copy.deepcopy(parent_product)
    product.parent_product = parent_product
    product = disconnect_data(product) if product.parsed.get('id') else product
    product.pk = None
    product.source_id = 0
    product.source_slug = ''
    if store is not None:
        product.store = store
    product.save()

    for supplier in parent_product.bigcommercesupplier_set.all():
        supplier.pk = None
        supplier.product = product
        supplier.store = product.store
        supplier.save()

        if supplier.is_default:
            product.set_default_supplier(supplier, commit=True)

    return product


def get_connected_options(product, split_factor):
    for option in product.parsed.get('options', []):
        if option['display_name'] == split_factor:
            return [v['label'] for v in option['option_values']]


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
    images = parent_data.get('images', [])
    variant_images = parent_data.get('variants_images', [])
    title = parent_data.get('title', '')

    for option in options:
        new_product = duplicate_product(product, product.store)
        new_data = {}
        new_data['title'] = '{} ({})'.format(title, option)

        variants = new_product.parsed.get('variants', [])
        new_data['variants'] = [v for v in variants if not v['title'] == split_factor]

        hashes = [h for h, variant in list(variant_images.items()) if variant == option]
        new_data['images'] = [i for i in images if hash_url_filename(i) in hashes]

        new_product.update_data(new_data)
        new_product.save()
        new_products.append(new_product)

    return new_products


def find_or_create_category(store, category_name='Shop All'):
    category_name = 'Shop All'
    r = store.request.get(
        url=store.get_api_url('v3/catalog/categories'),
        params={
            'name': category_name,
            'parent_id': '0',
        }
    )
    if r.ok and r.status_code != 204:
        categories = r.json()['data']
        if len(categories):
            return categories[0]

    r = store.request.post(
        url=store.get_api_url('v3/catalog/categories'),
        json={
            'name': category_name,
            'parent_id': 0,
        }
    )
    r.raise_for_status()
    return r.json()['data']


def get_store_from_request(request):
    store = None
    stores = request.user.profile.get_bigcommerce_stores()

    if request.GET.get('shop'):
        try:
            store = stores.get(shop=request.GET.get('shop'))
        except (BigCommerceStore.DoesNotExist, BigCommerceStore.MultipleObjectsReturned):
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

        except (PermissionDenied, BigCommerceStore.DoesNotExist):
            store = None

    if not store:
        store = stores.first()

    return store


def store_shipping_carriers(store):
    carriers = [
        {'usps': 'USPS'}, {'ups': 'UPS'}, {'fedex': 'FedEx'}, {'endicia': 'Endicia'},
        {'royalmail': 'Royal Mail'}, {'canadapost': 'Canada Post'}, {'auspost': 'Australia Post'},
        {'custom': 'Custom Provider'},
    ]

    return [{'id': list(c.keys()).pop(), 'title': list(c.values()).pop()} for c in carriers]


def get_order_line_fulfillment_status(order_line):
    if order_line['quantity'] == order_line['quantity_shipped']:
        return 'Fulfilled'


def get_shipping_carrier(shipping_carrier_name, store, carrier_id=None):
    cache_key = 'bigcommerce_shipping_carriers_{}_{}'.format(store.id, shipping_carrier_name)

    shipping_carriers = cache.get(cache_key)
    if shipping_carriers is not None:
        return shipping_carriers

    shipping_carriers_map = {}
    for i in store_shipping_carriers(store):
        # Shipping carrier id can be defined in user config
        if carrier_id and carrier_id == i['id']:
            return i
        shipping_carriers_map[i['title']] = i

    shipping_carrier = shipping_carriers_map.get(shipping_carrier_name, {})

    if shipping_carrier:
        cache.set(cache_key, shipping_carrier, timeout=3600)

    return shipping_carrier


def cache_fulfillment_data(order_tracks, orders_max=None):
    """
    Caches order data of given `BigCommerceOrderTrack` instances
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
        for order_id in order_ids:
            r = store.request.get(
                url=store.get_api_url('v2/orders', order_id),
            )
            r.raise_for_status()
            order = r.json()
            order['line_items'] = get_order_product_data(store, order)
            order['shipping_addresses'] = get_order_shipping_addresses(store, order)

            shipping_address = order['shipping_addresses'][0] if len(order['shipping_addresses']) > 0 else order['billing_address']
            country = shipping_address['country_iso2']

            args = store.id, order['id']
            cache_data['bigcommerce_country_{}_{}'.format(*args)] = country
            cache_data['bigcommerce_shipping_address_{}_{}'.format(*args)] = shipping_address['id']

            for line in order.get('line_items', []):
                cache_data['bigcommerce_quantity_{}_{}_{}'.format(store.id, order['id'], line['id'])] = line['quantity']

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

    # Keys are set by `bigcommerce_core.utils.cache_fulfillment_data`
    quantity = caches['orders'].get('bigcommerce_quantity_{store_id}_{order_id}_{line_id}'.format(**kwargs))
    country = caches['orders'].get('bigcommerce_country_{store_id}_{order_id}'.format(**kwargs))
    shipping_address_id = caches['orders'].get('bigcommerce_shipping_address_{store_id}_{order_id}'.format(**kwargs))

    shipping_carrier_name = leadgalaxy_utils.shipping_carrier(tracking_number)

    if country and country == 'US':
        if leadgalaxy_utils.is_chinese_carrier(tracking_number) or leadgalaxy_utils.shipping_carrier(tracking_number) == 'USPS':
            shipping_carrier_name = 'USPS'

    custom_tracking_carrier = user_config.get('bigcommerce_custom_tracking', {})
    custom_tracking_carrier_id = None
    if custom_tracking_carrier:
        custom_tracking_carrier_id = custom_tracking_carrier.get(str(order_track.store_id))

    shipping_carrier = get_shipping_carrier(shipping_carrier_name, order_track.store, carrier_id=custom_tracking_carrier_id)

    provider_id = shipping_carrier.get('id')
    provider_name = shipping_carrier.get('title')
    if provider_id == 'custom':
        provider_id = ''

    data = {
        'tracking_number': tracking_number,
        'order_address_id': shipping_address_id,
        'shipping_provider': provider_id,
        'shipping_method': provider_name,
        'items': [
            {
                'order_product_id': order_track.line_id,
                'quantity': quantity,
            }
        ]
    }

    return data


def order_id_from_name(store, order_name, default=None):
    ''' Get Order ID from Order Name '''

    order_rx = store.user.get_config('order_number', {}).get(str(store.id), '[0-9]+')
    order_number = re.findall(order_rx, order_name)
    if not order_number:
        return default

    r = store.request.get(
        url=store.get_api_url('v2/orders'),
        params={
            'id:like': order_number
        }
    )

    if r.ok and r.status_code != 204:
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

    params = {'id:in': ','.join(ids), 'limit': per_page, 'include': 'images,variants'}
    r = store.request.get(
        url=store.get_api_url('v3/catalog/products'),
        params=params
    )
    r.raise_for_status()

    products = {}
    for product in r.json()['data']:
        products[product['id']] = product

    new_tracker_orders = []
    for tracked in tracker_orders:
        tracked.product = product = products.get(tracked.product_id)
        if product:
            if not tracked.line:
                continue

            image = next(iter(product['images']), {})
            tracked.line['image'] = image.get('url_standard')

            variant_id = tracked.line.get('variant_id')
            if variant_id:
                tracked.variant = next(v for v in product['variants'] if v['id'] == variant_id)
                variant_image = tracked.variant.get('image_url')
                if variant_image:
                    tracked.line['image'] = variant_image

        new_tracker_orders.append(tracked)

    return new_tracker_orders


def get_tracking_orders(store, tracker_orders, per_page=50):
    ids = []
    for i in tracker_orders:
        ids.append(str(i.order_id))

    if not len(ids):
        return tracker_orders

    ids.sort()
    min_id = safe_int(ids[0])
    limit = 100
    # Reduce cost of queries with search split into "min_id" hops
    order_params = [{
        'limit': limit,
        'min_id': min_id,
    }]
    for order_id in ids:
        order_id = safe_int(order_id)
        if order_id > min_id + limit:  # BigCommerce Order ID are sequential int
            min_id = order_id
            order_params.append({
                'limit': limit,
                'min_id': min_id,
            })

    orders = {}
    lines = {}
    ids = list(set(ids))
    # All orders should be found
    for params in order_params:
        r = store.request.get(
            url=store.get_api_url('v2/orders'),
            params=params
        )
        r.raise_for_status()

        for order in r.json():
            if str(order['id']) in ids:
                ids.remove(str(order['id']))
                orders[order['id']] = order
                order['line_items'] = get_order_product_data(store, order)
                for line in order['line_items']:
                    lines['{}-{}'.format(order['id'], line['id'])] = line

    if len(ids):
        capture_message(f'Missing order ids for BigCommerce {store.pk}',
                        extra={'ids': ','.join(ids)})

    new_tracker_orders = []
    for tracked in tracker_orders:
        tracked.order = orders.get(tracked.order_id)
        tracked.line = lines.get('{}-{}'.format(tracked.order_id, tracked.line_id))

        if tracked.line:
            fulfillment_status = (get_order_line_fulfillment_status(tracked.line) or '').lower()
            tracked.line['fulfillment_status'] = fulfillment_status

            if tracked.bigcommerce_status != fulfillment_status:
                tracked.bigcommerce_status = fulfillment_status
                tracked.save()

        new_tracker_orders.append(tracked)

    return new_tracker_orders


def get_bigcommerce_products_count(store):
    return BigCommerceListQuery(store, '/v3/catalog/products').count()


def get_bigcommerce_products(store, page=1, limit=50, all_products=False, product_ids=None):
    if not all_products:
        params = {'page': page, 'limit': limit, 'include': 'variants,images'}
        if product_ids is not None:
            params['id:in'] = ','.join(product_ids)
        r = store.request.get(
            url=store.get_api_url('v3/catalog/products'),
            params=params
        )
        r.raise_for_status()
        for product in r.json()['data']:
            yield product
    else:
        limit = 250
        count = get_bigcommerce_products_count(store)

        if not count:
            return

        pages = int(ceil(count / float(limit)))
        for page in range(1, pages + 1):
            products = get_bigcommerce_products(store=store, page=page, limit=limit, all_products=False)
            for product in products:
                yield product


def smart_board_by_product(user, product):
    product_info = {
        'title': product.title,
        'tags': product.tags,
        'type': product.product_type,
    }
    for k, v in list(product_info.items()):
        if v:
            product_info[k] = [i.lower().strip() for i in v.split(',')]
        else:
            product_info[k] = []

    for i in user.bigcommerceboard_set.all():
        try:
            config = json.loads(i.config)
        except:
            continue

        product_added = False
        for j in ['title', 'tags', 'type']:
            if product_added:
                break

            if not len(config.get(j, '')) or not product_info[j]:
                continue

            for f in config.get(j, '').split(','):
                if f.lower() and f.lower().strip() in product_info[j]:
                    i.products.add(product)
                    product_added = True

                    break

        if product_added:
            i.save()


def bigcommerce_customer_address(order, aliexpress_fix=False, german_umlauts=False,
                                 aliexpress_fix_city=False, return_corrections=False,
                                 shipstation_fix=False):
    customer_address = {}
    shipping_address = order['shipping_addresses'][0] if len(order['shipping_addresses']) > 0 else order['billing_address']

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

    customer_address['name'] = '{} {}'.format(customer_address['first_name'], customer_address['last_name']).strip()
    customer_address['address1'] = customer_address.get('street_1')
    customer_address['address2'] = customer_address.get('street_2')
    customer_address['country_code'] = customer_address.get('country_iso2')
    customer_address['province_code'] = customer_address.get('state')
    customer_address['zip'] = customer_address.get('zip')

    customer_address['country'] = country_from_code(customer_address['country_iso2'], '')

    province = province_from_code(customer_address['country_iso2'], customer_address['province_code'])
    customer_address['province'] = unidecode(province) if type(province) is str else province

    if shipstation_fix:
        return order, supplement_customer_address(customer_address)

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

    if customer_address.get('company'):
        customer_address['name'] = '{} {} - {}'.format(customer_address['first_name'], customer_address['last_name'], customer_address['company'])

    if customer_address['country_code'] == 'JP':
        if customer_address.get('zip'):
            customer_address['zip'] = re.sub(r'[\n\r\t\._ -]', '', customer_address['zip'])

    correction = {}
    if aliexpress_fix:
        score_match = False
        if customer_address['country_code'] == 'JP':
            score_match = 0.3

        valide, correction = valide_aliexpress_province(
            customer_address['country'],
            customer_address['province'],
            customer_address['city'],
            auto_correct=True,
            score_match=score_match)

        if not valide:
            if support_other_in_province(customer_address['country']):
                customer_address['province'] = 'Other'

                if customer_address['country'].lower() == 'united kingdom' and customer_address['city']:
                    province = get_uk_province(customer_address['city'])
                    if province:
                        customer_address['province'] = province

                if customer_province and customer_address['province'] == 'Other':
                    customer_address['city'] = '{}, {}'.format(customer_address['city'], customer_province)

            elif aliexpress_fix_city:
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


def get_bigcommerce_order_data(store, order_id):
    r = store.request.get(
        url=store.get_api_url('v2/orders', order_id),
    )
    if r.ok:
        data = r.json()
        return data
    return ''


def get_latest_order_note(store, order_id):
    r = store.request.get(
        url=store.get_api_url('v2/orders', order_id),
    )

    if r.ok:
        data = r.json()
        return data.get('staff_notes', '')

    return ''


def add_bigcommerce_order_note(store, order_id, note):
    r = store.request.put(
        url=store.get_api_url('v2/orders', order_id),
        json={
            'staff_notes': note,
        }
    )
    r.raise_for_status()

    return r.json()


def get_order_track_product_id(store, order_id, line_id):
    order_key = 'bigcommerce_order_{}_{}_{}'.format(store.id, order_id, line_id)
    order = order_data_cache(order_key)
    if order:
        return order['product_source_id']

    r = store.request.get(
        url=store.get_api_url('v2/orders/{}/products'.format(order_id))
    )
    if r.ok:
        line_items = r.json()
        for line_item in line_items:
            if line_item['id'] == line_id:
                return line_item['product_id']


def get_product_data(store, product_ids=None):
    product_data_by_product_id = {}
    page = 1
    while page:
        params = {
            'page': page,
            'limit': store.user.get_config('_bigcommerce_product_limit', 25),
            'include': 'variants,images,options'
        }
        if product_ids is not None:
            if len(product_ids) == 0:
                return []
            product_ids = [str(product_id) for product_id in product_ids]
            params['id:in'] = ','.join(product_ids)

        r = store.request.get(
            url=store.get_api_url('v3/catalog/products'),
            params=params
        )
        r.raise_for_status()
        products = r.json()['data']
        pagination = r.json()['meta']['pagination']

        for product in products:
            product_data_by_product_id[product['id']] = product

        page = page + 1 if pagination['current_page'] != pagination['total_pages'] else 0

    return product_data_by_product_id


def get_unfulfilled_items(product_data):
    return [item for item in product_data if not item['quantity'] == item['quantity_shipped']]


def get_order_product_data(store, order):
    r = store.request.get(
        url=store.get_api_url('v2/orders/{}/products'.format(order['id']))
    )
    if r.status_code == 204:
        return []

    r.raise_for_status()
    return r.json()


def get_order_shipping_addresses(store, order):
    r = store.request.get(
        url=store.get_api_url('v2/orders/{}/shipping_addresses'.format(order['id']))
    )
    if r.status_code == 204:
        return []

    r.raise_for_status()
    return r.json()


def get_order_shipments(store, order):
    r = store.request.get(
        url=store.get_api_url('v2/orders/{}/shipments'.format(order['id']))
    )
    if r.status_code == 204:
        return []

    r.raise_for_status()
    return r.json()


def update_order_status(store, order_id, status, tries=3):
    while tries > 0:
        tries -= 1
        r = store.request.put(
            url=store.get_api_url('v2/orders/{}'.format(order_id)),
            json={'status_id': status}
        )
        if r.ok:
            break


class BigCommerceListQuery(object):
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
        self._response = self._store.request.get(
            url=self._store.get_api_url(self._endpoint),
            params=self._params
        )
        self._response.raise_for_status()

        return self._response

    def items(self):
        # Orders endpoint can return an empty response
        if self.response.status_code == 204:
            return []

        if isinstance(self.response.json(), dict):
            return self.response.json()['data']
        return self.response.json()

    def count(self):
        rep = self._store.request.get(
            url=self._store.get_api_url('v2/orders/count'),
        )

        rep.raise_for_status()

        try:
            return rep.json()['count']
        except:
            return 0

    def update_params(self, update):
        self._response = None
        self._params.update(update)

        return self

    def __len__(self):
        return self.count()


class BigCommerceListPaginator(SimplePaginator):
    def page(self, number):
        number = self.validate_number(number)
        self.current_page = number
        params = {'page': number, 'limit': self.per_page}
        # `self.object_list` is a `BigCommerceListQuery` instance
        items = list(self.object_list.update_params(params).items())

        return self._get_page(items, number, self)


class BigCommerceOrderUpdater:

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
            source = track.get_source_name()

        else:
            url = 'https://trade.aliexpress.com/order_detail.htm?orderId={}'.format(source_id)

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
            add_bigcommerce_order_note(self.store, self.order_id, new_note)

    def delay_save(self, countdown=None):
        from bigcommerce_core.tasks import order_save_changes

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

        self.store = BigCommerceStore.objects.get(id=data.get("store"))
        self.order_id = data.get("order")

        self.notes = data.get("notes")
