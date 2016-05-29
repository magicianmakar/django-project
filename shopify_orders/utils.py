from django.db.models import Q

# from raven.contrib.django.raven_compat.models import client as raven_client
import re
import arrow

from shopify_orders.models import ShopifySyncStatus, ShopifyOrder, ShopifyOrderLine


def safeInt(v, default=0):
    try:
        return int(v)
    except:
        return default


def get_customer_name(customer):
    return u'{} {}'.format(
        customer.get('first_name', ''),
        customer.get('last_name', '')).strip()


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
            resorted.append(order)

    return resorted


def update_shopify_order(store, data):
    try:
        sync_status = ShopifySyncStatus.objects.get(store=store)

        if sync_status.sync_status == 1:
            raise AssertionError('Store is being imported')

        elif sync_status.sync_status not in [2, 5]:  # Completed or Disabled
            return

    except ShopifySyncStatus.DoesNotExist:
        return

    customer = data.get('customer', {})
    address = data.get('shipping_address', {})

    order, created = ShopifyOrder.objects.update_or_create(
        order_id=data['id'],
        store=store,
        defaults={
            'user': store.user,
            'order_number': data['number'],
            'customer_id': customer.get('id', 0),
            'customer_name': get_customer_name(customer),
            'customer_email': customer.get('email'),
            'financial_status': data['financial_status'],
            'fulfillment_status': data['fulfillment_status'],
            'total_price': data['total_price'],
            'note': data.get('note'),
            'tags': data['tags'],
            'city': address.get('city'),
            'zip_code': address.get('zip'),
            'country_code': address.get('country_code'),
            'created_at': get_datetime(data['created_at']),
            'updated_at': get_datetime(data['updated_at']),
            'closed_at': get_datetime(data['closed_at']),
            'cancelled_at': get_datetime(data['cancelled_at']),
        }
    )

    for line in data.get('line_items', []):
        l, created = ShopifyOrderLine.objects.update_or_create(
            order=order,
            line_id=line['id'],
            defaults={
                'shopify_product': safeInt(line['product_id']),
                'title': line['title'],
                'price': line['price'],
                'quantity': line['quantity'],
                'variant_id': safeInt(line['variant_id']),
                'variant_title': line['variant_title']
            })

        l.product = store.shopifyproduct_set.filter(shopify_export__shopify_id=safeInt(line['product_id'])).first()
        l.save()


def delete_shopify_order(store, data):
    ShopifyOrder.objects.filter(store=store, order_id=data['id']).delete()


def is_store_synced(store, sync_type='orders'):
    ''' Return True if store orders have been synced '''
    try:
        sync_status = ShopifySyncStatus.objects.get(store=store)
        return sync_status.sync_status in [2, 5]
    except ShopifySyncStatus.DoesNotExist:
        return False


def is_store_sync_enabled(store, sync_type='orders'):
    ''' Return True if store orders are in sync and not disabled '''

    try:
        sync_status = ShopifySyncStatus.objects.get(store=store)
        return sync_status.sync_status == 2
    except ShopifySyncStatus.DoesNotExist:
        return False


def disable_store_sync(store):
    try:
        sync = ShopifySyncStatus.objects.get(store=store)

        # Disable only if import is Completed
        if sync.sync_status == 2:
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


def order_id_from_number(store, order_number):
    ''' Get Order ID from Order Number '''

    orders = ShopifyOrder.objects.filter(store=store)

    try:
        order_number = re.findall('[0-9]+', str(order_number))
        order_number = int(order_number[0])
    except:
        return None

    if order_number:
        orders = orders.filter(Q(order_number=order_number) |
                               Q(order_number=(order_number-1000)))

        for i in orders:
            return i.order_id

    return None
