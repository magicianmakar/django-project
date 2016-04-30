from django.core.cache import cache

# from raven.contrib.django.raven_compat.models import client as raven_client
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
        order = orders_map[i.order_id]
        if order:
            resorted.append(order)

    return resorted


def update_shopify_order(store, data):
    try:
        sync_status = ShopifySyncStatus.objects.get(store=store)
        if sync_status.sync_status != 2:
            print 'SHOPIFY ORDERS: Store: {} Not Synced (Status: {})'.format(store.title, sync_status.sync_status)
            return

    except ShopifySyncStatus.DoesNotExist:
        return

    assert sync_status.sync_status != 1, 'Store is being imported'

    customer = data.get('customer', {})
    address = data.get('shipping_address', {})

    products_map = cache.get('product_shopify_map_%d' % store.id)
    if products_map is None:
        products_map = store.shopifyproduct_set.exclude(shopify_export=None) \
                            .values_list('id', 'shopify_export__shopify_id') \
                            .order_by('created_at')

        products_map = dict(map(lambda a: (a[1], a[0]), products_map))

        # TODO: clear cache on Product connection change
        cache.set('product_shopify_map_%d' % store.id, products_map, timeout=1600)

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


def is_store_synced(store, sync_type='orders'):
    try:
        sync_status = ShopifySyncStatus.objects.get(store=store)
        return sync_status.sync_status == 2
    except ShopifySyncStatus.DoesNotExist:
        return False


def disable_store_sync(store):
    try:
        sync = ShopifySyncStatus.objects.get(store=store)
        sync.sync_status = 3
        sync.save()
    except:
        pass
