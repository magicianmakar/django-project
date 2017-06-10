import re

from django.db.models import Q
from django.shortcuts import get_object_or_404

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


def get_product_api_data(saved_data):
    data = {'name': saved_data['title']}
    data['status'] = 'publish' if saved_data['published'] else 'draft'
    data['price'] = str(saved_data['price'])
    data['regular_price'] = str(saved_data['compare_at_price'])
    data['weight'] = str(saved_data['weight'])
    data['description'] = saved_data.get('description')
    data['images'] = []
    for position, src in enumerate(saved_data.get('images', [])):
        data['images'].append({'src': src, 'name': src, 'position': position})

    variants = saved_data.get('variants', [])
    if variants:
        data['type'] = 'variable'
        data['attributes'] = []
        for num, variant in enumerate(variants):
            name, options = variant.get('title'), variant.get('values', [])
            attribute = {'position': num + 1, 'name': name, 'options': options, 'variation': True}
            data['attributes'].append(attribute)

    return data


def get_image_id_by_hash(store_data):
    image_id_by_hash = {}
    for image in store_data.get('images', []):
        hash_ = hash_url_filename(image['name'])
        image_id_by_hash[hash_] = image['id']

    return image_id_by_hash


def get_variants_api_data(saved_data, image_id_by_hash):
    variants = saved_data.get('variants', [])
    variants_sku = saved_data.get('variants_sku', {})
    variant_list = []

    for variant in variants:
        title = variant.get('title')
        options = variant.get('values', [])

        for option in options:
            data = {
                'sku': variants_sku.get(option),
                'attributes': [
                    {'name': title, 'option': option},
                ],
            }

            if saved_data.get('compare_at_price'):
                data['regular_price'] = str(saved_data['compare_at_price'])
                data['sale_price'] = str(saved_data['price'])
            else:
                data['regular_price'] = str(saved_data['price'])

            for image_hash, variant_option in saved_data.get('variants_images', {}).items():
                if variant_option == option and image_hash in image_id_by_hash:
                    data['image'] = {'id': image_id_by_hash[image_hash]}

            variant_list.append(data)

    return variant_list


def add_store_tags_to_data(data, store, tags):
    if not tags:
        data['tags'] = []
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

        data['tags'] = [{'id': tag_id} for tag_id in tag_ids]

    return data
