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


def update_product_api_data(api_data, data):
    api_data['name'] = data['title']
    api_data['status'] = 'publish' if data['published'] else 'draft'
    api_data['price'] = str(data['price'])
    api_data['regular_price'] = str(data['compare_at_price'])
    api_data['weight'] = str(data['weight'])
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
    variants_sku = data.get('variants_sku', {})
    variant_list = []

    for variant in variants:
        title = variant.get('title')
        options = variant.get('values', [])

        for option in options:
            api_data = {
                'sku': variants_sku.get(option),
                'description': option,
                'attributes': [
                    {'name': title, 'option': option},
                ],
            }

            if data.get('compare_at_price'):
                api_data['regular_price'] = str(data['compare_at_price'])
                api_data['sale_price'] = str(data['price'])
            else:
                api_data['regular_price'] = str(data['price'])

            for image_hash, variant_option in data.get('variants_images', {}).items():
                if variant_option == option and image_hash in image_id_by_hash:
                    api_data['image'] = {'id': image_id_by_hash[image_hash]}

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
