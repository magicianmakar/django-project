from django.core.cache import cache

import re
import arrow
import requests
from unidecode import unidecode

from shopify_orders.models import ShopifySyncStatus, ShopifyOrder, ShopifyOrderLine
from shopified_core.province_helper import load_uk_provincess, missing_province


def safeInt(v, default=0):
    try:
        return int(v)
    except:
        return default


def str_max(text, max_len):
    if not text:
        return ''
    else:
        return text[:max_len]


def get_customer_name(customer):
    return u'{} {}'.format(
        customer.get('first_name', ''),
        customer.get('last_name', '')).strip()


def ensure_title(text):
    """ Ensure the given string start with an upper case letter """

    try:
        if text.encode().strip():
            is_lower = all([c.islower() or not c.isalpha() for c in text])
            if is_lower:
                return text.title()
    except:
        pass

    return text


def get_customer_address(order):
    customer_address = None

    if 'shipping_address' not in order \
            and order.get('customer') and order.get('customer').get('default_address'):
        order['shipping_address'] = order['customer'].get('default_address')

    if 'shipping_address' in order:
        customer_address = {}  # Aliexpress doesn't allow unicode
        shipping_address = order['shipping_address']
        for k in shipping_address.keys():
            if shipping_address[k] and type(shipping_address[k]) is unicode:
                customer_address[k] = unidecode(shipping_address[k])
            else:
                customer_address[k] = shipping_address[k]

        if not customer_address['province']:
            if customer_address['country'] == 'United Kingdom':
                province = load_uk_provincess().get(customer_address['city'].lower().strip(), '')
                if not province:
                    missing_province(customer_address['city'])

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

        customer_address['name'] = ensure_title(customer_address['name'])

        if customer_address['company']:
            customer_address['name'] = u'{} - {}'.format(customer_address['name'], customer_address['company'])

    return customer_address


def get_datetime(isodate, default=None):
    return arrow.get(isodate).datetime if isodate else default


def sort_orders(orders, page):
    orders_map = {}
    resorted = []

    for i in orders:
        orders_map[i['id']] = i

    for i in page:
        order = orders_map.get(i.order_id)
        if order:
            order['db_updated_at'] = arrow.get(i.updated_at).timestamp
            resorted.append(order)

    return resorted


def update_shopify_order(store, data, sync_check=True):
    if sync_check:
        try:
            sync_status = ShopifySyncStatus.objects.get(store=store)

            if sync_status.sync_status == 1:
                sync_status.add_pending_order(data['id'])
                return

            elif sync_status.sync_status not in [2, 5, 6]:
                # Retrn if not Completed, Disabled or in Reset
                return

        except ShopifySyncStatus.DoesNotExist:
            return

    address = data.get('shipping_address', data.get('customer', {}).get('default_address', {}))
    customer = data.get('customer', address)

    order, created = ShopifyOrder.objects.update_or_create(
        order_id=data['id'],
        store=store,
        defaults={
            'user': store.user,
            'order_number': data['number'],
            'customer_id': customer.get('id', 0),
            'customer_name': str_max(get_customer_name(customer), 255),
            'customer_email': str_max(customer.get('email'), 255),
            'financial_status': data['financial_status'],
            'fulfillment_status': data['fulfillment_status'],
            'total_price': data['total_price'],
            'note': data.get('note'),
            'tags': data['tags'],
            'city': str_max(address.get('city'), 63),
            'zip_code': str_max(address.get('zip'), 31),
            'country_code': str_max(address.get('country_code'), 31),
            'items_count': len(data.get('line_items', [])),
            'created_at': get_datetime(data['created_at']),
            'updated_at': get_datetime(data['updated_at']),
            'closed_at': get_datetime(data['closed_at']),
            'cancelled_at': get_datetime(data['cancelled_at']),
        }
    )

    for line in data.get('line_items', []):
        cache_key = 'export_product_{}_{}'.format(store.id, line['product_id'])
        product = cache.get(cache_key)
        if product is None:
            product = store.shopifyproduct_set.filter(shopify_id=safeInt(line['product_id'])).first()
            cache.set(cache_key, product.id if product else 0, timeout=300)
        else:
            product = store.shopifyproduct_set.get(id=product) if product != 0 else None

        ShopifyOrderLine.objects.update_or_create(
            order=order,
            line_id=line['id'],
            defaults={
                'shopify_product': safeInt(line['product_id']),
                'title': line['title'],
                'price': line['price'],
                'quantity': line['quantity'],
                'variant_id': safeInt(line['variant_id']),
                'variant_title': line['variant_title'],
                'fulfillment_status': line['fulfillment_status'],
                'product': product
            })


def update_line_export(store, product_id):
    """
    Update ShopifyOrderLine.product when a supplier is added or changed
    :param product_id: Shopify Product ID
    """

    product = store.shopifyproduct_set.filter(shopify_id=product_id).first()

    ShopifyOrderLine.objects.filter(order__store=store, shopify_product=product_id) \
                            .update(product=product)


def delete_shopify_order(store, data):
    ShopifyOrder.objects.filter(store=store, order_id=data['id']).delete()


def is_store_synced(store, sync_type='orders'):
    ''' Return True if store orders have been synced '''
    try:
        sync_status = ShopifySyncStatus.objects.get(store=store)
        return sync_status.sync_status in [2, 5, 6]
    except ShopifySyncStatus.DoesNotExist:
        return False


def is_store_sync_enabled(store, sync_type='orders'):
    ''' Return True if store orders are in sync and not disabled '''

    try:
        sync_status = ShopifySyncStatus.objects.get(store=store)
        return sync_status.sync_status in [2, 6]
    except ShopifySyncStatus.DoesNotExist:
        return False


def disable_store_sync(store):
    try:
        sync = ShopifySyncStatus.objects.get(store=store)

        # Disable only if import is Completed
        if sync.sync_status == 2 and sync.sync_status != 6:
            sync.sync_status = 5
            sync.save()

    except:
        pass


def enable_store_sync(store):
    try:
        sync = ShopifySyncStatus.objects.get(store=store)

        if sync.sync_status == 5:
            sync.sync_status = 2
            sync.save()

    except:
        pass


def change_store_sync(store):
    try:
        sync = ShopifySyncStatus.objects.get(store=store)

        if sync.sync_status == 5:
            sync.sync_status = 2
            sync.save()

    except:
        pass


def order_id_from_name(store, order_name, default=None):
    ''' Get Order ID from Order Name '''

    orders = ShopifyOrder.objects.filter(store=store)

    order_rx = store.user.get_config('order_number', {}).get(str(store.id), '[0-9]+')
    order_number = re.findall(order_rx, order_name)
    if not order_number:
        return default

    order_number = order_number[0]
    if len(order_number) > 7:
        # Order name should contain less than 7 digits
        return default

    params = {
        'status': 'any',
        'fulfillment_status': 'any',
        'financial_status': 'any',
        'fields': 'id',
        'name': order_name
    }

    rep = requests.get(
        url=store.get_link('/admin/orders.json', api=True),
        params=params
    )

    if rep.ok:
        orders = rep.json()['orders']

        if len(orders):
            return orders.pop()['id']

    return default
