import re
import requests
from requests.auth import HTTPBasicAuth
from django.conf import settings
from raven.contrib.django.raven_compat.models import client as raven_client

from shopified_core.utils import app_link

PRICE_MONITOR_BASE = '{}/api'.format(settings.PRICE_MONITOR_HOSTNAME)


def aliexpress_variants(product_id):
    variants_api_url = '{}/products/{}/variants'.format(PRICE_MONITOR_BASE, product_id)
    rep = requests.get(
        url=variants_api_url,
        auth=HTTPBasicAuth(settings.PRICE_MONITOR_USERNAME, settings.PRICE_MONITOR_PASSWORD)
    )
    rep.raise_for_status()
    return rep.json()


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
            auth=HTTPBasicAuth(settings.PRICE_MONITOR_USERNAME, settings.PRICE_MONITOR_PASSWORD)
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


def variant_index(product, sku, variants):
    # sku = 14:173#66Blue;5:361386 <OptionGroup>:<OptionID>#<OptionTitle>;
    original_sku = sku
    found_variant_id = None
    variants_map = product.get_variant_mapping(for_extension=True)

    options = []
    for s in sku.split(';'):
        m = re.match(r"(?P<option_group>\w+):(?P<option_id>\w+)#?(?P<option_title>.+)?", s)
        options.append(m.groupdict())
    sku = ';'.join('{}:{}'.format(option['option_group'], option['option_id']) for option in options)

    for variant_id, variant in variants_map.iteritems():
        found = True
        for variant_option in variant:
            mapped_title = variant_option.get('title')
            mapped_sku = variant_option.get('sku')
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
            elif variant.get('sku') in sku or variant.get('sku') in original_sku:
                return idx
    return None
