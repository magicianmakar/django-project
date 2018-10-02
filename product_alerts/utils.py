import re
import requests
from django.conf import settings
from raven.contrib.django.raven_compat.models import client as raven_client

from shopified_core.utils import app_link

PRICE_MONITOR_BASE = '{}/api'.format(settings.PRICE_MONITOR_HOSTNAME)


def aliexpress_variants(product_id):
    variants_api_url = '{}/products/{}/variants'.format(PRICE_MONITOR_BASE, product_id)
    rep = requests.get(
        url=variants_api_url,
        auth=(settings.PRICE_MONITOR_USERNAME, settings.PRICE_MONITOR_PASSWORD)
    )
    rep.raise_for_status()
    return rep.json()


def reset_product_monitor(store):
    if store.__class__.__name__ == 'ShopifyStore' and store.shopifyproduct_set.count() < 2000:
        store.shopifyproduct_set.filter(monitor_id__gt=0).update(monitor_id=0)
    elif store.__class__.__name__ == 'CommerceHQStore' and store.products.count() < 2000:
        store.products.filter(monitor_id__gt=0).update(monitor_id=0)


def unmonitor_store(store):
    if store.__class__.__name__ == 'ShopifyStore':
        dropified_type = 'shopify'
    elif store.__class__.__name__ == 'CommerceHQStore':
        dropified_type = 'chq'

    rep = requests.delete(
        url='{}/products'.format(PRICE_MONITOR_BASE),
        params={'dropified_type': dropified_type, 'store': store.id},
        auth=(settings.PRICE_MONITOR_USERNAME, settings.PRICE_MONITOR_PASSWORD)
    )

    rep.raise_for_status()

    reset_product_monitor(store)


def monitor_product(product, stdout=None):
    """
    product_id: Source Product ID (ex. Aliexpress ID)
    store_id: Source Store ID (ex. Aliexpress Store ID)
    """
    try:
        supplier = product.default_supplier

        if not supplier.is_aliexpress:
            #  Not connected or not an Aliexpress product
            product.monitor_id = -1
            product.save()
            return

        store_id = supplier.get_store_id()
        if not store_id:
            store_id = 0

        product_id = supplier.get_source_id()
        if not product_id:
            # Product doesn't have Source Product ID
            product.monitor_id = -3
            product.save()
            return
    except:
        product.monitor_id = -5
        product.save()
        return

    if product.__class__.__name__ == 'ShopifyProduct':
        dropified_type = 'shopify'
    elif product.__class__.__name__ == 'CommerceHQProduct':
        dropified_type = 'chq'

    webhook_url = app_link('webhook/price-monitor/product', product=product.id, dropified_type=dropified_type)
    monitor_api_url = '{}/products'.format(PRICE_MONITOR_BASE)
    rep = None
    try:
        post_data = {
            'product_id': product_id,
            'store_id': store_id,
            'dropified_id': product.id,
            'dropified_type': dropified_type,
            'dropified_store': product.store_id,
            'dropified_user': product.user_id,
            'url': product.default_supplier.product_url,
            'webhook': webhook_url,
        }

        rep = requests.post(
            url=monitor_api_url,
            json=post_data,
            auth=(settings.PRICE_MONITOR_USERNAME, settings.PRICE_MONITOR_PASSWORD)
        )
        rep.raise_for_status()

        data = rep.json()
        product.monitor_id = data['id']
        product.save()

    except Exception as e:
        raven_client.captureException()

        if stdout:
            if not rep:
                stdout.write(' * API Call error: {}'.format(repr(e)))
            else:
                stdout.write(' * Attach Product ({}) Exception: {} \nResponse: {}'.format(
                    product.id, repr(e), rep.text))

        return


def parse_sku(sku):
    options = []
    if sku:
        for s in sku.split(';'):
            m = re.match(r"(?P<option_group>\w+):(?P<option_id>\w+)#?(?P<option_title>.+)?", s)
            option = m.groupdict()
            if not option.get('option_title'):
                option['option_title'] = ''
            options.append(option)
    return options


def variant_index(product, sku, variants=None):
    original_sku = sku or ''
    found_variant_id = None
    variants_map = product.get_variant_mapping(for_extension=True)

    options = parse_sku(sku)
    sku = ';'.join('{}:{}'.format(option['option_group'], option['option_id']) for option in options)

    for variant_id, variant in variants_map.iteritems():
        found = True
        for variant_option in variant:
            if type(variant_option) is dict:
                mapped_title = variant_option.get('title')
                mapped_sku = variant_option.get('sku')
            else:
                mapped_title = variant_option
                mapped_sku = ''

            exists = False
            for option in options:
                option_id = option['option_id']
                option_title = option['option_title']
                if mapped_sku and option_id in mapped_sku:
                    exists = True
                if mapped_title and mapped_title == option_title:
                    exists = True
            if not exists:
                found = False
                break
        if found:
            found_variant_id = variant_id
            break
    if variants is None:
        return found_variant_id
    if found_variant_id is not None:
        for idx, variant in enumerate(variants):
            if variant.get('id') == int(found_variant_id):
                return idx
    else:
        for idx, variant in enumerate(variants):
            variant_values = variant.get('variant')
            if variant_values:  # CHQ Product
                found = True
                for i, value in enumerate(variant_values):
                    if value != options[i]['option_title']:
                        found = False
                if found:
                    return idx
            elif variant.get('sku') and (variant['sku'] in sku or variant['sku'] in original_sku):
                return idx
    return None
