import re
import requests
from django.conf import settings
from raven.contrib.django.raven_compat.models import client as raven_client

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


def unmonitor_store(store):
    if store.__class__.__name__ == 'ShopifyStore':
        dropified_type = 'shopify'
    elif store.__class__.__name__ == 'CommerceHQStore':
        dropified_type = 'chq'

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


def parse_supplier_sku(sku):
    options = []
    if sku:
        for s in sku.split(';'):
            m = re.match(r"(?P<option_group>\w+):(?P<option_id>\w+)#?(?P<option_title>.+)?", s)
            option = m.groupdict()
            if not option.get('option_title'):
                option['option_title'] = ''
            options.append(option)
    return options


def variant_index_from_supplier_sku(product, sku, variants=None, ships_from_id=None, ships_from_title=None):
    original_sku = sku or ''
    found_variant_id = None
    variants_map = product.get_variant_mapping(for_extension=True)

    if not sku:
        if variants is None:
            if len(variants_map) == 1:
                return list(variants_map.keys())[0]
            else:
                return None
        elif len(variants) == 1:
            return 0
        else:
            return None

    options = parse_supplier_sku(sku)
    sku = ';'.join('{}:{}'.format(option['option_group'], option['option_id']) for option in options)

    for variant_id, variant in variants_map.items():
        found = True
        ships_from_mapped = True if ships_from_id is None else False
        no_variant = False
        for variant_option in variant:
            if type(variant_option) is dict:
                mapped_title = variant_option.get('title')
                mapped_sku = variant_option.get('sku')
                if len(variant) == 1 and mapped_title == 'Default Title':
                    no_variant = True
                if variant_option.get('extra', False):
                    continue
            else:
                mapped_title = variant_option
                mapped_sku = ''

            exists = False
            for option in options:
                option_id = option['option_id']
                option_title = option['option_title']
                if mapped_sku and re.search(r"\b{}\b".format(option_id), mapped_sku):
                    exists = True
                if mapped_title and mapped_title == option_title:
                    exists = True
                if exists:
                    if ships_from_id == option_id:
                        ships_from_mapped = True
                    break
            if not exists:
                found = False
                break
        if no_variant and not found:
            if len(options) == 0:  # no variant option
                found = True
            elif len(options) == 1 and ships_from_id is not None:  # ships from is the only option
                found = True
        if found:
            if ships_from_mapped:
                found_variant_id = variant_id
            elif ships_from_title == 'China':
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
                if ships_from_id is None or ships_from_title == 'China':
                    return idx
    return None


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
