import copy
import json
import re
from unidecode import unidecode
from collections import Counter

import arrow

from django.core.cache import cache
from django.db.models import Q
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404
from lib.exceptions import capture_exception

from shopified_core import permissions
from shopified_core.utils import (
    safe_int,
    products_filter,
    hash_url_filename,
    get_top_most_commons,
    get_first_valid_option,
)
from shopified_core.shipping_helper import (
    load_uk_provincess,
    country_from_code,
    province_from_code,
    get_uk_province,
    valide_aliexpress_province,
    support_other_in_province,
)
import leadgalaxy.utils as leadgalaxy_utils
from supplements.utils import supplement_customer_address

from .models import GrooveKartStore, GrooveKartProduct, GrooveKartBoard


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

    res = products_filter(res, request.GET)

    if sort:
        if re.match(r'^-?(title|price)$', sort):
            res = res.order_by(sort)

    return res


def get_store_categories(store):
    try:
        categories_url = store.get_api_url('list_categories.json')
        response = store.request.post(categories_url)
        response.raise_for_status()

        result = response.json()
        # Id can be "int as string" or None
        return [c for c in result['categories'] if c.get('id')]
    except:
        capture_exception()
        return []


def get_or_create_category_by_title(store, category_title):
    # GrooveKart Lite stores use Home Category
    if store.is_lite:
        return 1

    if safe_int(category_title, None) is not None:
        return safe_int(category_title)

    category_title_lower = category_title.lower()

    def search(categories, category_title_lower):
        for category in categories:
            if category['title'] and category['title'].lower() == category_title_lower:
                return safe_int(category['id'])

    categories = get_store_categories(store)
    category_id = search(categories, category_title_lower)

    if category_id is None:
        result = store.request.post(store.get_api_url('create_categories.json'), json={'category': {'title': category_title}})
        # Create Categories JSON is list of existing categories
        categories = result.json()
        category_id = search(categories.get('categories', []), category_title_lower)

    return category_id


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

    for i in user.groovekartboard_set.all():
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


def gkart_customer_address(order, aliexpress_fix=False, shipstation_fix=False):
    customer_address = {}

    shipping_address = order.get('shipping_address', {})

    customer_address['first_name'] = shipping_address.get('first_name')
    customer_address['last_name'] = shipping_address.get('last_name')
    customer_address['name'] = f"{customer_address['first_name']} {customer_address['last_name']}"
    customer_address['address1'] = shipping_address.get('address1', '')
    customer_address['address2'] = shipping_address.get('address2', '')
    customer_address['city'] = shipping_address.get('city', '')
    customer_address['country_code'] = shipping_address.get('country_code', '')
    customer_address['province_code'] = shipping_address.get('province', '')
    customer_address['zip'] = shipping_address.get('zip', '')
    customer_address['country'] = country_from_code(customer_address['country_code'], '')
    customer_address['province'] = province_from_code(customer_address['country_code'], customer_address['province_code'])
    customer_address['phone'] = shipping_address.get('phone', '')

    for key in list(customer_address.keys()):
        if customer_address[key] is str:
            customer_address[key] = unidecode(customer_address[key])

    if shipstation_fix:
        return supplement_customer_address(customer_address)

    customer_province = customer_address['province']
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

    return customer_address


def set_gkart_order_note(store, order_id, note):
    api_url = store.get_api_url('orders.json')
    r = store.request.post(api_url, json={
        'order_id': safe_int(order_id),
        'action': 'delete_note' if len(note) == 0 else 'add_note',
        'note': note
    })
    r.raise_for_status()

    return r.ok


def get_gkart_order(store, order_id):
    api_url = store.get_api_url('orders.json')
    r = store.request.post(api_url, json={
        'order_id': safe_int(order_id)
    })
    r.raise_for_status()
    if r.ok:
        return r.json()
    return ''


def order_id_from_name(store, order_reference, default=None):
    ''' Get Order ID from Order Name '''

    order_rx = store.user.get_config('order_number', {}).get(str(store.id), '[0-9]+')
    order_number = re.findall(order_rx, order_reference)

    return order_number if order_number else default


def get_tracking_orders(store, tracker_orders):
    ids = [str(track.order_id) for track in tracker_orders]
    orders = {}
    lines = {}
    page = 1
    limit = 50

    while page:
        params = {
            'action': 'search_orders',
            'offset': limit * (page - 1),
            'limit': limit,
            'ids': ','.join(ids),
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


def map_images(product, product_data):
    variants_images = {}
    image_options_map = {}
    product_data_images = product_data.get('images', [])[:]
    images = [img['url'] for img in product_data_images]
    variants = product_data.get('variants', [])
    valid_options = [variant['variant_name'] for variant in variants]

    for variant in variants:
        src = product_data.get('cover_image')

        if variant.get('image'):
            image_id = variant['image']['id']
            for product_data_image in product_data_images:
                if product_data_image['id'] == image_id:
                    src = product_data_image['url']
                    break

        if not src:
            continue

        hash_src = hash_url_filename(src)
        variant_option = variant['variant_name']
        image_options_map.setdefault(hash_src, []).append(variant_option)
        options = image_options_map.get(hash_src, [])
        most_commons = Counter(options).most_common()

        # Most common attributes associated with the image
        if most_commons:
            top_most_commons = get_top_most_commons(most_commons)
            if len(top_most_commons) == 1:
                # Sets the image to its most popular option
                option, count = top_most_commons[0]
                variants_images[hash_src] = option
            else:
                # In case of a tie, assigns the first valid option
                variants_images[hash_src] = get_first_valid_option(top_most_commons, valid_options)

        if src not in images:
            images.append(src)

    product.update_data({'images': images})
    product.update_data({'variants_images': variants_images})


def map_variants(product, product_data):
    variants_map = {}

    for variant in product_data.get('variants', []):
        variants_map.setdefault(variant['group_name'], []).append(variant['variant_name'])

    variants = [{'title': title, 'values': values} for title, values in variants_map.items()]

    product.update_data({'variants': variants})


def disconnect_data(product):
    product_data = product.retrieve()
    map_images(product, product_data)
    map_variants(product, product_data)
    data = product.parsed
    product.data = json.dumps(data)

    return product


def duplicate_product(product, store=None):
    parent_product = GrooveKartProduct.objects.get(id=product.id)
    product = copy.deepcopy(parent_product)
    product.parent_product = parent_product
    product = disconnect_data(product) if product.is_connected else product
    product.pk = None
    product.source_id = 0
    product.store = store
    product.save()

    for supplier in parent_product.groovekartsupplier_set.all():
        supplier.pk = None
        supplier.product = product
        supplier.store = product.store
        supplier.save()

        if supplier.is_default:
            product.set_default_supplier(supplier, commit=True)

    return product


def get_variant_values(product, split_factor):
    options_key = 'variant_options' if product.is_connected else 'variants'
    variants = product.parsed.get(options_key, [])

    for variant in variants:
        if variant['title'] == split_factor:
            return variant['values']

    return []


def get_variant_images(product, option):
    variant_images = []
    data = product.parsed
    product_images = data.get('images', [])
    variants_images = data.get('variants_images', {})
    options = list(variants_images.values())
    if option in options:
        hashed_images = [key for key, value in list(variants_images.items()) if value == option]
        for product_image in product_images:
            if hash_url_filename(product_image) in hashed_images:
                variant_images.append(product_image)

    return variant_images if variant_images else product_images


def split_product(product, split_factor, store=None):
    new_products = []
    options = get_variant_values(product, split_factor)
    parent_data = product.parsed
    title = parent_data.get('title', '')

    for option in options:
        new_product = duplicate_product(product, product.store)
        variants = new_product.parsed.get('variants', [])
        new_data = {}
        new_data['title'] = '{} ({})'.format(title, option)
        new_data['variants'] = [v for v in variants if not v['title'] == split_factor]
        new_data['images'] = get_variant_images(new_product, option)
        new_product.update_data(new_data)
        new_product.save()
        new_products.append(new_product)

    return new_products


def cache_fulfillment_data(order_tracks, orders_max=None):
    """
    Caches order data of given `GrooveKartOrderTrack` instances
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

        url = store.get_api_url('orders.json')
        r = store.request.post(url, json={
            'action': 'search_orders',
            'ids': include
        })

        orders = []
        if r.ok:
            result = r.json()
            if 'orders' in result:
                orders = result['orders']

            # Single order search returns as dict
            if not isinstance(result, list):
                if result.get('id') is not None:  # Order Found
                    orders = [result]
        elif r.status_code == 404:
            orders = []
        else:
            r.raise_for_status()

        for order in orders:
            key = store.id, order['id']
            fulfillment = order.get('trackings', [])
            cache_data['gkart_auto_fulfillment_{}_{}'.format(*key)] = fulfillment if len(fulfillment) > 0 else None

    cache.set_many(cache_data, timeout=3600)

    return list(cache_data.keys())


def order_track_fulfillment(order_track, user_config=None):
    user_config = {} if user_config is None else user_config
    tracking_number = order_track.source_tracking
    send_email = user_config.get('send_shipping_confirmation')

    if order_track.custom_tracking_url:
        carrier_name = leadgalaxy_utils.shipping_carrier(tracking_number)
        carrier_name = 'AfterShip' if not carrier_name else carrier_name
        carrier_url = order_track.get_tracking_link()
        carrier_url = carrier_url if not isinstance(carrier_url, list) else ','.join([c[1] for c in carrier_url])
    else:
        carrier_name = ''
        carrier_url = ''

    tracking_numbers = []
    carrier_names = []
    carrier_urls = []
    cache_key = 'gkart_auto_fulfillment_{}_{}'.format(order_track.store.id, order_track.order_id)
    fulfillment = cache.get(cache_key)

    if fulfillment:
        if fulfillment['tracking_number']:
            tracking_numbers = fulfillment['tracking_number'].split(',')
            tracking_numbers = [str(number) for number in tracking_numbers]
        if fulfillment.get('carrier_name'):
            carrier_names = fulfillment['carrier_name'].split(',')
        if fulfillment.get('carrier_url'):
            carrier_urls = fulfillment['carrier_url'].split(',')

    changed = False
    if tracking_number not in tracking_numbers:
        changed = True
        tracking_numbers.append(tracking_number)
        carrier_names.append(carrier_name)
        carrier_urls.append(carrier_url)

    tracking_numbers = ','.join(tracking_numbers)
    carrier_names = ','.join(carrier_names)
    carrier_urls = ','.join(carrier_urls)

    fulfillment_data = {
        'order_id': order_track.order_id,
        'tracking_number': tracking_numbers,
        'carrier_name': carrier_names if not carrier_urls else '',
        'carrier_url': carrier_urls,
        'send_email': send_email != 'no',  # Can also be auto
    }

    cache.set(cache_key, fulfillment_data, timeout=3600)
    return changed, fulfillment_data


def get_variant_value(label, value, color_textures=None):
    if not color_textures:
        color_textures = {}

    texture = color_textures.get(value)
    if texture:
        # TODO: Sending correct label(not Color) erases variant_name
        return ('Color', {'variant_group_type': 'color', 'variant_name': value, 'texture': texture})
    else:
        return (label, {'variant_group_type': 'radio', 'variant_name': value})


def get_orders_page_default_date_range(timezone):
    start = arrow.get(timezone.now()).replace(days=-30).format('MM/DD/YYYY')
    end = arrow.get(timezone.now()).replace(days=+1).format('MM/DD/YYYY')

    return start, end


def update_product_images(product, images):
    if images:
        store = product.store
        endpoint = store.get_api_url('products.json')

        for index, image in enumerate(images):
            if 'groovekart.com' in image:
                continue

            # GKart replaces images when providing their id
            replace_image = image.split('#')
            if len(replace_image) == 2:
                image_id = re.findall(r'image_id=(\d+)', replace_image[1])
                if image_id:
                    image_id = image_id[0]
                    api_data = {
                        'product': {
                            'action': 'replace_image',
                            'product_id': product.source_id,
                            'image_id': image_id,
                            'image': {
                                'src': replace_image[0],
                                'position': 0,
                                'cover': 1 if product.get_cover_image_id() == image_id else 0
                            },
                        }
                    }
                    r = store.request.post(endpoint, json=api_data)
                    r.raise_for_status()
                    continue

            # Include new images
            api_data = {
                'product': {
                    'id': product.source_id,
                    'image': {'src': image, 'position': index},
                }
            }

            r = store.request.post(endpoint, json=api_data)
            r.raise_for_status()


def fix_gkart_image(image):
    if image:
        image = image.replace('-large_default2x', '')

        # Matches: "945.jpg?v=1571331426" or "945.jpg"
        return re.sub(r'(\d+)(\.\w+(\?v=\S+)?)$', r'\1-large_default\2', image)

    return image


class OrderListQuery(object):
    def __init__(self, store, params=None):
        self._endpoint = 'orders.json'
        self._store = store
        # Action search_orders only returns results if we use at least one filter
        self._params = {'action': 'search_orders', 'reference': '%'}
        if params:
            self._params.update(params)

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
            capture_exception()
            return []

    def count(self, attempts=1):
        if self._params.get('order_id'):
            return 1

        # TODO: This endpoint needs to be separated or it will eventually take forever to bring the orders
        url = self._store.get_api_url(self._endpoint)

        for _ in reversed(range(attempts)):
            try:
                r = self._store.request.post(url, json={
                    **self._params,
                    'action': 'search_orders'
                })
                r.raise_for_status()
                result = r.json()
                if 'no orders found' in result.get('Error', '').lower():
                    return 0
                else:
                    return result['orders_count']

            except:
                if attempts > 0:
                    continue

                capture_exception()
                return 0

    def update_params(self, update):
        self._params.update(update)

        return self

    def __len__(self):
        return self.count()


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
