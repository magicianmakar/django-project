import re
import json
import itertools
import urllib

from measurement.measures import Weight
from decimal import Decimal, ROUND_HALF_UP

from django.db.models import Q
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.core.paginator import Paginator
from django.core.exceptions import PermissionDenied

from shopified_core import permissions
from shopified_core.utils import safeInt, safeFloat, hash_url_filename

from .models import WooProduct, WooStore


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

    res = filter_products(res, request.GET)

    if sort:
        if re.match(r'^-?(title|price)$', sort):
            res = res.order_by(sort)

    return res


def format_woo_errors(e):
    if not hasattr(e, 'response'):
        return 'Server Error'

    return e.response.json().get('message', '')


def update_product_api_data(api_data, data, store):
    api_data['name'] = data['title']
    api_data['status'] = 'publish' if data['published'] else 'draft'
    api_data['price'] = str(data['price'])
    api_data['regular_price'] = str(data['compare_at_price'])
    api_data['weight'] = str(match_weight(data['weight'], data['weight_unit'], store))
    api_data['description'] = data.get('description')

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


@transaction.atomic
def duplicate_product(product, store=None):
    parent_product = WooProduct.objects.get(id=product.id)
    product.pk = None
    product.parent_product = parent_product
    product.source_id = 0
    product.store = store

    if product.parsed.get('id'):
        data = product.parsed
        data.pop('id')
        data.pop('published')
        data['status'] = 'draft'
        data['variants'] = []
        data['images'] = data.pop('original_images', data['images'])

        for attribute in data.pop('attributes', []):
            title, values = attribute['name'], attribute['options']
            data['variants'].append({'title': title, 'values': values})

        product.data = json.dumps(data)

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
        new_data['title'] = '{} ({})'.format(title, option)

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
    rep = store.request.get(store.get_api_url('shipping-carriers'), params={'size': 100})
    if rep.ok:
        return rep.json()['items']
    else:
        carriers = [
            {1: 'USPS'}, {2: 'UPS'}, {3: 'FedEx'}, {4: 'LaserShip'},
            {5: 'DHL US'}, {6: 'DHL Global'}, {7: 'Canada Post'}
        ]

        return map(lambda c: {'id': c.keys().pop(), 'title': c.values().pop()}, carriers)


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
        return not self._response is None

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


class WooListPaginator(Paginator):
    def page(self, number):
        number = self.validate_number(number)
        params = {'page': number, 'per_page': self.per_page}
        # `self.object_list` is a `WooListQuery` instance
        items = self.object_list.update_params(params).items()

        return self._get_page(items, number, self)
