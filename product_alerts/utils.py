import re

from django.conf import settings
from raven.contrib.django.raven_compat.models import client as raven_client

import requests
from munch import Munch

from shopified_core.utils import app_link, url_join, safe_float, safe_int


def get_supplier_variants(supplier_type, product_id):
    if supplier_type != 'aliexpress':
        return []
    rep = requests.get(
        url=url_join(settings.PRICE_MONITOR_HOSTNAME, '/api/products', product_id, '/variants'),
        auth=(settings.PRICE_MONITOR_USERNAME, settings.PRICE_MONITOR_PASSWORD)
    )

    rep.raise_for_status()
    return rep.json()


def reset_product_monitor(store):
    if store.__class__.__name__ == 'ShopifyStore' and store.shopifyproduct_set.count() < 2000:
        store.shopifyproduct_set.filter(monitor_id__gt=0).update(monitor_id=0)
    elif store.__class__.__name__ == 'CommerceHQStore' and store.products.count() < 2000:
        store.products.filter(monitor_id__gt=0).update(monitor_id=0)
    elif store.__class__.__name__ == 'GrooveKartStore' and store.products.count() < 2000:
        store.products.filter(monitor_id__gt=0).update(monitor_id=0)
    elif store.__class__.__name__ == 'WooStore' and store.products.count() < 2000:
        store.products.filter(monitor_id__gt=0).update(monitor_id=0)


def unmonitor_store(store):
    if store.__class__.__name__ == 'ShopifyStore':
        dropified_type = 'shopify'
    elif store.__class__.__name__ == 'CommerceHQStore':
        dropified_type = 'chq'
    elif store.__class__.__name__ == 'GrooveKartStore':
        dropified_type = 'gkart'
    elif store.__class__.__name__ == 'WooStore':
        dropified_type = 'woo'

    rep = requests.delete(
        url=url_join(settings.PRICE_MONITOR_HOSTNAME, '/api/products'),
        params={'dropified_type': dropified_type, 'store': store.id},
        auth=(settings.PRICE_MONITOR_USERNAME, settings.PRICE_MONITOR_PASSWORD)
    )

    rep.raise_for_status()

    reset_product_monitor(store)


def is_monitorable(product):
    monitor_id = 0
    try:
        supplier = product.default_supplier

        if not supplier.is_aliexpress:
            #  Not connected or not an Aliexpress product
            monitor_id = -1

        product_id = supplier.get_source_id()
        if not product_id:
            # Product doesn't have Source Product ID
            monitor_id = -3
    except:
        monitor_id = -5

    return monitor_id >= 0 and product.is_connected and product.store.is_active


def update_product_monitor(monitor_id, supplier):
    store_id = supplier.get_store_id()
    if not store_id:
        store_id = 0
    product_id = supplier.get_source_id()

    post_data = {
        'url': supplier.product_url,
        'product_id': product_id,
        'store_id': store_id,
    }

    rep = requests.patch(
        url=url_join(settings.PRICE_MONITOR_HOSTNAME, '/api/products/', monitor_id),
        data=post_data,
        auth=(settings.PRICE_MONITOR_USERNAME, settings.PRICE_MONITOR_PASSWORD)
    )
    rep.raise_for_status()


def delete_product_monitor(monitor_id):
    rep = requests.delete(
        url=url_join(settings.PRICE_MONITOR_HOSTNAME, '/api/products/', monitor_id),
        auth=(settings.PRICE_MONITOR_USERNAME, settings.PRICE_MONITOR_PASSWORD)
    )

    rep.raise_for_status()


def monitor_product(product, stdout=None):
    """
    product_id: Source Product ID (ex. Aliexpress ID)
    store_id: Source Store ID (ex. Aliexpress Store ID)
    """
    original_monitor_id = product.monitor_id
    if is_monitorable(product):
        if original_monitor_id and original_monitor_id > 0:
            # Update original monitor
            update_product_monitor(original_monitor_id, product.default_supplier)
            return
    else:
        if original_monitor_id and original_monitor_id > 0:
            # Delete original monitor
            delete_product_monitor(original_monitor_id)
            product.monitor_id = 0
            product.save()
        return

    supplier = product.default_supplier
    store_id = supplier.get_store_id()
    if not store_id:
        store_id = 0
    product_id = supplier.get_source_id()

    if product.__class__.__name__ == 'ShopifyProduct':
        dropified_type = 'shopify'
    elif product.__class__.__name__ == 'CommerceHQProduct':
        dropified_type = 'chq'
    elif product.__class__.__name__ == 'GrooveKartProduct':
        dropified_type = 'gkart'
    elif product.__class__.__name__ == 'WooProduct':
        dropified_type = 'woo'

    webhook_url = app_link('webhook/price-monitor/product', product=product.id, dropified_type=dropified_type)
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
            url=url_join(settings.PRICE_MONITOR_HOSTNAME, '/api/products'),
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


def parse_supplier_sku(sku, sort=False, remove_shipping=False):
    options = []
    if sku:
        for s in sku.split(';'):
            m = re.match(r"(?P<option_group>\w+):(?P<option_id>\w+)#?(?P<option_title>.+)?", s)
            option = m.groupdict()
            if not option.get('option_title'):
                option['option_title'] = ''
            options.append(option)

    if sort:
        options = sorted(options, key=lambda k: k['option_group'])

    if remove_shipping:
        options = [k for k in options if k['option_group'] != '200007763']

    return options


def match_sku_with_mapping_sku(sku, mapping):
    """ Match a SKU str with a mapping return by get_variant_mapping

    Args:
        sku: str
        mapping: list(dict), ex: [{title: Red, sku: 1:1}, {title: XL, sku: 2:10}]
    """

    remove_shipping = len(parse_supplier_sku(sku)) != len(mapping)

    # Remove title from Aliexpress SKU
    clean_ali_sku = ';'.join(f"{option['option_group']}:{option['option_id']}"
                             for option in parse_supplier_sku(sku, sort=True, remove_shipping=remove_shipping))

    # Remove title and groupd ID for older Aliexpress products mapping
    clean_ali_sku_ids = ';'.join(sorted(option['option_id']
                                 for option in parse_supplier_sku(sku, sort=True, remove_shipping=remove_shipping)))

    # Remove "sku-n-" from old Aliexpress mapping and join them to look like Aliexpress SKU
    mapping_skus = ';'.join(sorted([i['sku'].split('-').pop() for i in mapping if i.get('sku')]))

    return clean_ali_sku == mapping_skus or \
        clean_ali_sku_ids == mapping_skus


def match_sku_title_with_mapping_title(sku, mapping):
    """ Match a title with a mapping return by get_variant_mapping

    Args:
        title: str
        mapping: list(dict), ex: [{title: Red, sku: 1:1}, {title: XL, sku: 2:10}]
    """

    ali_sku_titles = ';'.join(sorted(option['option_title'] for option in parse_supplier_sku(sku, sort=True)))

    mapping_titles = ';'.join(sorted([i['title'] for i in mapping if i.get('title')]))

    return ali_sku_titles.lower() == mapping_titles.lower()


def match_sku_with_shopify_sku(sku, shopify_sku):
    remove_shipping = len(parse_supplier_sku(sku)) != len(parse_supplier_sku(shopify_sku))

    clean_sku = ';'.join(f"{option['option_group']}:{option['option_id']}"
                         for option in parse_supplier_sku(sku, sort=True, remove_shipping=remove_shipping))

    clean_shopify_sku = ';'.join(f"{option['option_group']}:{option['option_id']}"
                                 for option in parse_supplier_sku(shopify_sku, sort=True, remove_shipping=remove_shipping))

    # clean_first_sku_ids = ';'.join(sorted(option['option_id'] for option in parse_supplier_sku(sku, sort=True)))
    # clean_second_sku_ids = ';'.join(sorted(option['option_id'] for option in parse_supplier_sku(shopify_sku, sort=True)))

    return clean_sku == clean_shopify_sku


def match_sku_title_with_shopify_variant_title(sku, variant):
    """ Match a title with a mapping return by get_variant_mapping

    Args:
        title: str
        mapping: list(dict), ex: [{title: Red, sku: 1:1}, {title: XL, sku: 2:10}]
    """

    ali_sku_titles = ';'.join(sorted(option['option_title'] for option in parse_supplier_sku(sku, sort=True)))

    options = []
    if 'option1' in variant:
        # Shopify
        options = [j for j in [variant['option1'], variant['option2'], variant['option3']] if bool(j)]
    elif 'variant' in variant:
        # CHQ
        options = variant['variant']
    elif 'variant_name' in variant:
        # GKart, TODO: need handling other variant names, also SKU
        options = [j for j in [variant['variant_name']] if bool(j)]

    shopify_titles = ';'.join(sorted(options))

    return ali_sku_titles.lower() == shopify_titles.lower()


def variant_index_from_supplier_sku(product, sku, variants=None):
    match = Munch(dict(
        sku_mapping_sku=[],
        sku_shopify_sku=[],
        title_mapping_title=[],
        title_shopify_title=[],
    ))

    if not sku:
        if variants and len(variants) == 1:
            return 0

    for idx, variant in enumerate(variants):
        variant_id = variant['id'] if 'id' in variant else variant.get('id_product_variant')  # TODO: excption for GKart
        mapping = product.get_variant_mapping(variant_id, for_extension=True)
        if mapping and match_sku_with_mapping_sku(sku, mapping):
            match.sku_mapping_sku.append(idx)

        elif variant.get('sku') and match_sku_with_shopify_sku(sku, variant.get('sku')):
            match.sku_shopify_sku.append(idx)

        elif mapping and match_sku_title_with_mapping_title(sku, mapping):
            match.title_mapping_title.append(idx)

        elif match_sku_title_with_shopify_variant_title(sku, variant):
            match.title_shopify_title.append(idx)

    if match.sku_mapping_sku:
        return match.sku_mapping_sku.pop()
    elif match.sku_shopify_sku:
        return match.sku_shopify_sku.pop()
    elif match.title_mapping_title:
        return match.title_mapping_title.pop()
    elif match.title_shopify_title:
        return match.title_shopify_title.pop()


def calculate_price(user, old_value, new_value, current_price, current_compare_at, price_update_method, markup_rules):
    new_price = None
    new_compare_at = None

    if price_update_method == 'global_markup':
        auto_margin = safe_float(user.get_config('auto_margin', '').rstrip('%'))
        auto_compare_at = safe_float(user.get_config('auto_compare_at', '').rstrip('%'))
        if auto_margin > 0:
            new_price = new_value + ((new_value * auto_margin) / 100.0)
            new_price = round(new_price, 2)
        if auto_compare_at > 0:
            new_compare_at = new_value + ((new_value * auto_compare_at) / 100.0)
            new_compare_at = round(new_compare_at, 2)

    if price_update_method == 'custom_markup':
        for markup_rule in markup_rules:
            if new_value >= markup_rule.min_price and (new_value < markup_rule.max_price or markup_rule.max_price < 0):
                markup_value = markup_rule.markup_value
                markup_compare_value = markup_rule.markup_compare_value

                if markup_value > 0:
                    if markup_rule.markup_type == 'margin_percent':
                        new_price = new_value + new_value * (markup_value / 100.0)
                    elif markup_rule.markup_type == 'margin_amount':
                        new_price = new_value + markup_value
                    elif markup_rule.markup_type == 'fixed_amount':
                        new_price = markup_value
                    new_price = round(new_price, 2)

                if markup_compare_value > 0:
                    if markup_rule.markup_type == 'margin_percent':
                        new_compare_at = new_value + new_value * (markup_compare_value / 100.0)
                    elif markup_rule.markup_type == 'margin_amount':
                        new_compare_at = new_value + markup_compare_value
                    elif markup_rule.markup_type == 'fixed_amount':
                        new_compare_at = markup_compare_value
                    new_compare_at = round(new_compare_at, 2)

    if price_update_method == 'same_margin':
        new_price = round((current_price * new_value) / old_value, 2)
        if current_compare_at:
            new_compare_at = round((current_compare_at * new_value) / old_value, 2)

    auto_margin_cents = safe_int(user.get_config('auto_margin_cents'), None)
    if new_price is not None and auto_margin_cents is not None and auto_margin_cents >= 0:
        new_price = safe_float(str(int(new_price)) + '.' + ('0' if auto_margin_cents <= 9 else '') + str(auto_margin_cents))
        new_price = round(new_price, 2)

    auto_compare_at_cents = safe_int(user.get_config('auto_compare_at_cents'), None)
    if new_compare_at is not None and auto_compare_at_cents is not None and auto_compare_at_cents >= 0:
        new_compare_at = safe_float(str(int(new_compare_at)) + '.' + ('0' if auto_compare_at_cents <= 9 else '') + str(auto_compare_at_cents))
        new_compare_at = round(new_compare_at, 2)

    return [new_price, new_compare_at]
