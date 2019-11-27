import re
import copy
import json
import itertools

import requests

from unidecode import unidecode

from django.conf import settings
from django.shortcuts import get_object_or_404
from django.db.models import Q
from django.db import transaction
from django.core.cache import cache
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator

import leadgalaxy.utils as leadgalaxy_utils

from shopified_core import permissions
from shopified_core.utils import (
    safe_int,
    products_filter,
    hash_url_filename,
)
from shopified_core.shipping_helper import (
    load_uk_provincess,
    country_from_code,
    province_from_code
)

from .models import GearBubbleStore, GearBubbleProduct, GearBubbleBoard


def gearbubble_products(request, post_per_page=25, sort=None, board=None, store='n'):
    store = request.GET.get('store', store)
    sort = request.GET.get('sort')

    user_stores = request.user.profile.get_gear_stores(flat=True)
    res = GearBubbleProduct.objects.select_related('store') \
                           .filter(user=request.user.models_user) \
                           .filter(Q(store__in=user_stores) | Q(store=None))

    if store:
        if store == 'c':  # connected
            res = res.exclude(source_id=0)
        elif store == 'n':  # non-connected
            res = res.filter(source_id=0)

            in_store = safe_int(request.GET.get('in'))
            if in_store:
                in_store = get_object_or_404(GearBubbleStore, id=in_store)
                res = res.filter(store=in_store)

                permissions.user_can_view(request.user, in_store)
        else:
            store = get_object_or_404(GearBubbleStore, id=store)
            res = res.filter(source_id__gt=0, store=store)

            permissions.user_can_view(request.user, store)

    if board:
        res = res.filter(gearbubbleboard=board)
        permissions.user_can_view(request.user, get_object_or_404(GearBubbleBoard, id=board))

    res = products_filter(res, request.GET)

    if sort:
        if re.match(r'^-?(title|price)$', sort):
            res = res.order_by(sort)

    return res


def format_gear_errors(e):
    if not hasattr(e, 'response'):
        return 'Server Error'

    return e.response.json().get('error', '')


def get_image_hash_to_etag_map(images):
    image_hash_to_etag_map = {}

    for img in images:
        image_hash = hash_url_filename(img['src'])
        image_key = 'gearbubble_image_etag_{}'.format(image_hash)
        image_etag = cache.get(image_key)

        if not image_etag:
            r = requests.head(img['src'])
            r.raise_for_status()
            image_etag = r.headers['ETag']
            cache.set(image_key, image_etag)

        image_hash_to_etag_map[image_hash] = image_etag

    return image_hash_to_etag_map


def map_images(product, product_data):
    images = product_data.get('images', [])[:]
    image_hash_to_etag_map = get_image_hash_to_etag_map(images)
    variants_images = {}
    deletables = []

    for variant in product_data.get('variants', []):
        option = variant['options'][0]
        src = variant['image']['src']
        hash_src = hash_url_filename(src)
        hash_src_sha = image_hash_to_etag_map[hash_src]
        for img in images:
            hash_img_src = hash_url_filename(img['src'])
            hash_img_sha = image_hash_to_etag_map[hash_img_src]
            same_url = hash_img_src == hash_src
            same_image = hash_img_sha == hash_src_sha
            if not img['variant_id'] and not same_url and same_image:
                variants_images[hash_img_src] = option
                deletables.append(src)
                break
        else:
            variants_images[hash_src] = option

    images = [img['src'] for img in images if img['src'] not in deletables]
    product.update_data({'images': images})
    product.update_data({'variants_images': variants_images})


def map_variants(product, product_data):
    variants = []

    for option in product_data.get('options', []):
        title, values = option['name'], option['values'].split(',')
        variants.append({'title': title, 'values': values})

    product.update_data({'variants': variants})


def disconnect_data(product):
    product_data = product.get_product_data()
    map_images(product, product_data)
    map_variants(product, product_data)
    data = product.parsed
    data.pop('source_id')
    data.pop('source_slug')
    product.data = json.dumps(data)

    return product


@transaction.atomic
def duplicate_product(product, store=None):
    parent_product = GearBubbleProduct.objects.get(id=product.id)
    product = copy.deepcopy(parent_product)
    product.parent_product = parent_product
    product = disconnect_data(product) if product.parsed.get('source_id') else product
    product.pk = None
    product.source_id = 0
    product.source_slug = ''
    product.store = store
    product.save()

    for supplier in parent_product.gearbubblesupplier_set.all():
        supplier.pk = None
        supplier.product = product
        supplier.store = product.store
        supplier.save()

        if supplier.is_default:
            product.set_default_supplier(supplier, commit=True)

    return product


def get_variant_values(product, split_factor):
    if product.is_connected:
        for option in product.parsed.get('options', []):
            if option['name'] == split_factor:
                return option['values'].split(',')
    else:
        for variant in product.parsed.get('variants', []):
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


def get_store_from_request(request):
    store = None
    stores = request.user.profile.get_gear_stores()

    if request.GET.get('shop'):
        try:
            store = stores.get(shop=request.GET.get('shop'))
        except (GearBubbleStore.DoesNotExist, GearBubbleStore.MultipleObjectsReturned):
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

        except (PermissionDenied, GearBubbleStore.DoesNotExist):
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

    return [{'id': list(c.keys()).pop(), 'title': list(c.values()).pop()} for c in carriers]


def get_orders_from_store(store):
    orders = []
    page = 1
    while page:
        r = store.request.get(store.get_api_url('private_orders'), params={'page': page})

        if r.ok:
            orders += r.json()['data']['orders']
            page += 1

        if r.status_code == 404:
            return orders

        r.raise_for_status()


def get_shipping_carrier_name(store, carrier_id):
    shipping_carriers = store_shipping_carriers(store)
    for carrier in shipping_carriers:
        if carrier['id'] == carrier_id:
            return carrier['title']


def gear_customer_address(order):
    customer_address = {}

    name = order.get('name', '').split(' ')

    customer_address['name'] = name
    customer_address['first_name'] = name[0]
    customer_address['last_name'] = ' '.join(name[1:])
    customer_address['address1'] = order.get('address1', '')
    customer_address['address2'] = order.get('address2', '')
    customer_address['city'] = order.get('city', '')
    customer_address['country_code'] = order.get('country', '')
    customer_address['province_code'] = order.get('state', '')
    customer_address['zip'] = order.get('zip_code', '')
    customer_address['country'] = country_from_code(customer_address['country_code'], '')
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


def order_id_from_name(store, order_name, default=None):
    ''' Get Order ID from Order Name '''

    order_rx = store.user.get_config('order_number', {}).get(str(store.id), '[0-9]+')
    order_number = re.findall(order_rx, order_name)

    return order_number if order_number else default


def get_tracking_orders(store, tracker_orders):
    ids = [str(track.order_id) for track in tracker_orders]
    orders = {}
    lines = {}
    page = 1

    while page:
        params = {'page': page, 'limit': 50, 'ids': ','.join(ids)}
        r = store.request.get(store.get_api_url('private_orders'), params=params)

        if r.ok:
            for order in r.json()['orders']:
                orders[order['id']] = order

                for line in order.get('line_items', []):
                    lines['{}-{}'.format(order['id'], line['id'])] = line

            page += 1

        if r.status_code == 404:
            break

        r.raise_for_status()

    new_tracker_orders = []

    for tracked in tracker_orders:
        tracked.order = orders.get(tracked.order_id)
        tracked.line = lines.get('{}-{}'.format(tracked.order_id, tracked.line_id))

        if tracked.line:
            fulfillment_status = 'fulfilled' if tracked.order['shipped'] else None
            tracked.line['fulfillment_status'] = fulfillment_status

            if tracked.gearbubble_status != fulfillment_status:
                tracked.gearbubble_status = fulfillment_status
                tracked.save()

        new_tracker_orders.append(tracked)

    return new_tracker_orders


def add_details_from_product_data(line, product_data):
    product_data = GearBubbleProduct.update_variant_properties(product_data)
    option_set = set(line['variant_option'].values())
    line['image'] = next(iter(product_data.get('images', [])), {})
    line['name'] = product_data['title']

    for variant in product_data.get('variants', []):
        if option_set == set(variant['options']):
            line['image'] = variant['image']
            description, name = variant['description'], product_data['title']
            line['name'] = '({}) {}'.format(description, name).rstrip()
            break

    return line


def get_tracking_products(store, tracker_orders):
    ids = [str(track.order['vendor_product_id']) for track in tracker_orders]
    products = {}
    page = 1

    while page:
        params = {'page': page, 'limit': 50, 'ids': ','.join(ids)}
        r = store.request.get(store.get_api_url('private_products'), params=params)

        if r.ok:
            for product in r.json()['products']:
                products[product['id']] = product

            page += 1

        if r.status_code == 404:
            break

        r.raise_for_status()

    new_tracker_orders = []
    for tracked in tracker_orders:
        tracked.product = product = products.get(tracked.order['vendor_product_id'])
        if product:
            tracked.line = add_details_from_product_data(tracked.line, product)
            new_tracker_orders.append(tracked)

    return new_tracker_orders


def get_fulfillment(store, order_id):
    api_url = store.get_api_url('orders/{}/private_fulfillments'.format(order_id))
    r = store.request.get(api_url)
    r.raise_for_status()
    fulfillment = next(iter(r.json()['fulfillments']), None)

    return fulfillment


def cache_fulfillment_data(order_tracks, orders_max=None):
    """
    Caches order data of given `GearBubbleOrderTrack` instances
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
        page = 1

        while page:
            params = {'page': page, 'limit': 50, 'ids': include}
            r = store.request.get(store.get_api_url('private_orders'), params=params)

            if not r.ok:
                if r.status_code == 404:
                    break
                r.raise_for_status()

            orders = r.json()['orders']

            for order in orders:
                key = store.id, order['id']
                cache_data['gear_auto_country_{}_{}'.format(*key)] = order['country']
                cache_data['gear_auto_fulfillment_{}_{}'.format(*key)] = get_fulfillment(store, order['id'])

            page += 1

    cache.set_many(cache_data, timeout=3600)

    return list(cache_data.keys())


def order_track_fulfillment(order_track, user_config=None):
    user_config = {} if user_config is None else user_config
    tracking_number = order_track.source_tracking
    tracking_company = leadgalaxy_utils.shipping_carrier(tracking_number)
    country = cache.get('gear_auto_country_{}_{}'.format(order_track.store.id, order_track.order_id))

    if country and country == 'US':
        if leadgalaxy_utils.is_chinese_carrier(tracking_number) or leadgalaxy_utils.shipping_carrier(tracking_number) == 'USPS':
            tracking_company = 'USPS'

    tracking_company = 'AfterShip' if not tracking_company else tracking_company
    tracking_numbers = []
    tracking_companies = []
    fulfillment = cache.get('gear_auto_fulfillment_{}_{}'.format(order_track.store.id, order_track.order_id))

    if fulfillment:
        if fulfillment['tracking_number']:
            tracking_numbers = fulfillment['tracking_number'].split(',')
            tracking_numbers = [str(number) for number in tracking_numbers]
        if fulfillment['tracking_company']:
            tracking_companies = fulfillment['tracking_company'].split(',')

    changed = False

    if tracking_number not in tracking_numbers:
        changed = True
        tracking_numbers.append(tracking_number)
        tracking_companies.append(tracking_company)

    tracking_numbers = ','.join(tracking_numbers)
    tracking_companies = ','.join(tracking_companies)

    return changed, {'tracking_number': tracking_numbers, 'tracking_company': tracking_companies}


def set_gear_order_note(store, order_id, note):
    api_url = store.get_api_url('private_orders/{}'.format(order_id))
    r = store.request.put(api_url, json={'order': {'id': order_id, 'note': note}})
    r.raise_for_status()

    return r.ok


def get_product_export_data(product):
    data = product.parsed
    vendor_product = {}
    vendor_product['title'] = data.get('title', '')
    vendor_product['cost'] = data.get('price') or 0
    vendor_product['available_qty'] = data.get('available_qty', settings.GEARBUBBLE_DEFAULT_QTY)
    vendor_product['body_html'] = data.get('description', '')
    vendor_product['tags'] = data.get('tags', '')
    vendor_product['weight'] = data.get('weight') or 0
    vendor_product['weight_unit'] = data.get('weight_unit', '')
    vendor_product['images'] = [{'src': src} for src in data.get('images', [])]

    if data.get('variants', []):
        vendor_product['options'] = []
        vendor_product['variants'] = []
        options = []

        for i, variant in enumerate(data['variants'], start=1):
            vendor_product['options'].append({'option{}'.format(i): variant.get('title', '')})
            options.append(variant.get('values', []))

        for variant_product in itertools.product(*options):
            variant = {}
            variant['cost'] = data.get('price') or 0
            variant['compare_at_price'] = data.get('compare_at_price')
            variant['available_qty'] = data.get('available_qty', settings.GEARBUBBLE_DEFAULT_QTY)
            variant['weight'] = data.get('weight') or 0
            variant['weight_unit'] = data.get('weight_unit', 'g')

            for i, option in enumerate(variant_product, start=1):
                variant['option{}'.format(i)] = option

                if not variant.get('image'):
                    option_images = get_variant_images(product, option)
                    variant['image'] = next(iter(option_images), '')

            vendor_product['variants'].append(variant)

    return vendor_product


def get_product_update_data(product, data):
    api_data = {'id': product.source_id}
    api_data['title'] = data.get('title', '')
    api_data['cost'] = data.get('price') or 0
    api_data['compare_at_price'] = data.get('compare_at_price', '')
    api_data['body_html'] = data.get('description') or '<p></p>'
    api_data['tags'] = data.get('tags', '')
    api_data['weight'] = data.get('weight') or 0
    api_data['weight_unit'] = data.get('weight_unit', '')

    effect_on_current_images = get_effect_on_current_images(product, data)

    if not effect_on_current_images == 'same':
        if effect_on_current_images == 'change':
            # Should replace the images after the old ones are deleted
            api_data['images'] = [{'src': src} for src in data.get('images', [])]
        if effect_on_current_images == 'add':
            update_images = set(data.get('images', []))
            current_images = set(product.parsed.get('images', []))
            # Adds new images to the current image set
            api_data['images'] = [{'src': src} for src in (update_images - current_images)]

    if data.get('variants', []):
        api_data['variants'] = []
        for variant_data in data['variants']:
            variant = {}
            variant['id'] = variant_data['id']
            variant['cost'] = variant_data['price'] or 0
            variant['compare_at_price'] = variant_data['compare_at_price']
            variant['sku'] = variant_data['sku']

            if effect_on_current_images == 'change':
                # Updating the product's images would require that all images,
                # including the variant images, are cleared first before the
                # new images are added. For this reason, the variant image
                # must be assigned to the variant again or else it will
                # disappear with the old images.
                variant['image'] = variant_data['image']

            api_data['variants'].append(variant)

    return api_data


def get_effect_on_current_images(product, product_data):
    update_images = set(product_data.get('images', []))
    current_images = set(product.parsed.get('images', []))

    if not update_images.issuperset(current_images):
        # The update will change the current set of images
        return 'change'

    if update_images.issuperset(current_images) and not (update_images == current_images):
        # The update will keep the current set of images and add new ones
        return 'add'

    return 'same'


class OrderListQuery(object):
    def __init__(self, store, params=None):
        self._endpoint = 'private_orders'
        self._store = store
        self._params = {} if params is None else params

    def items(self):
        url = self._store.get_api_url(self._endpoint)
        r = self._store.request.get(url, params=self._params)

        if r.ok:
            return r.json()['orders']
        elif r.status_code == 404:
            return []
        else:
            r.raise_for_status()

    def count(self):
        url = self._store.get_api_url('{}/{}'.format(self._endpoint.rstrip('/'), 'count'))
        r = self._store.request.get(url, params=self._params)
        r.raise_for_status()

        return r.json()['count']

    def update_params(self, update):
        self._params.update(update)

        return self


class OrderListPaginator(Paginator):
    def page(self, number):
        number = self.validate_number(number)
        params = {'page': number, 'limit': self.per_page}
        # `self.object_list` is an `OrderListQuery` instance
        items = list(self.object_list.update_params(params).items())

        return self._get_page(items, number, self)


class GearOrderUpdater:

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
            set_gear_order_note(self.store, self.order_id, new_note)

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

        self.store = GearBubbleStore.objects.get(id=data.get("store"))
        self.order_id = data.get("order")

        self.notes = data.get("notes")
