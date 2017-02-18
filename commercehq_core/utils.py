import json

import requests
import arrow

from .models import CommerceHQProduct


def fetch_resource(store, path):
    session = requests.Session()
    # Send an unauthorized request first or API will return a 500.
    # This could be related to a bug on the API side.
    session.head(path)
    session.auth = store.api_key, store.password
    response = session.get(path)
    session.close()

    return response


def add_or_update_product(store, data):
    return CommerceHQProduct.objects.update_or_create(
        product_id=data['id'],
        store=store,
        defaults={
            'title': data.get('title'),
            'is_multi': bool(data.get('is_multi')),
            'product_type': data.get('type'),
            'textareas': json.dumps(data.get('textareas', [])),
            'shipping_weight': data.get('shipping_weight', 0.0),
            'auto_fulfillment': bool(data.get('auto_fulfilment')),
            'track_inventory': bool(data.get('track_inventory')),
            'vendor': data.get('vendor'),
            'tags': data.get('tags', ''),
            'sku': data.get('sku', ''),
            'seo_meta': data.get('seo_meta', ''),
            'seo_title': data.get('seo_title', ''),
            'seo_url': data.get('seo_url', ''),
            'is_template': bool(data.get('is_template')),
            'template_name': data.get('template_name', ''),
            'is_draft': bool(data.get('is_draft')),
            'price': data.get('price'),
            'compare_price': data.get('compare_price'),
            'options': data.get('options', ''),
            'variants': data.get('variants', ''),
            'created_at': arrow.get(data.get('created_at')).datetime,
            'updated_at': arrow.get(data.get('update_at')).datetime,
        }
    )


def sync_products(store):
    products = []
    response = fetch_resource(store, '{}/api/v1/products'.format(store.url))
    products_data = response.json()['items']

    for product_data in products_data:
        product, created = add_or_update_product(store, product_data)
        products.append(product)

    return products
