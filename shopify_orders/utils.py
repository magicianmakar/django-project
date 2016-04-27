from django.core.cache import cache

# from raven.contrib.django.raven_compat.models import client as raven_client
import arrow

from shopify_orders.models import ShopifySyncStatus, ShopifyOrder, ShopifyOrderLine


def get_customer_name(customer):
    return u'{} {}'.format(
        customer.get('first_name', ''),
        customer.get('last_name', '')).strip()


def update_shopify_order(store, data):
    try:
        sync_status = ShopifySyncStatus.objects.get(store=store)
        if sync_status.sync_status != 2:
            print 'SHOPIFY ORDERS: Store: {} Not Synced (Status: {})'.format(store.title, sync_status.sync_status)
            return

    except ShopifySyncStatus.DoesNotExist:
        return

    customer = data.get('customer', {})
    address = data.get('shipping_address', {})

    products_map = cache.get('product_shopify_map_%d' % store.id)
    if products_map is None:
        products_map = store.user.shopifyproduct_set.values_list('id', 'shopify_export__shopify_id')
        products_map = dict(map(lambda a: (a[1], a[0]), products_map))

        # TODO: clear cache on Product connection change
        cache.set('product_shopify_map_%d' % store.id, products_map, timeout=1600)

    order, created = ShopifyOrder.objects.update_or_create(
        order_id=data['id'],
        defaults={
            'user': store.user,
            'store': store,
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
            'created_at': arrow.get(data['created_at']).datetime,
            'updated_at': arrow.get(data['updated_at']).datetime,
            'closed_at': arrow.get(data['closed_at']).datetime,
        }
    )

    for line in data.get('line_items', []):
        l, created = ShopifyOrderLine.objects.update_or_create(
            order=order,
            line_id=line['id'],
            defaults={
                'shopify_product': line['product_id'],
                'title': line['title'],
                'price': line['price'],
                'quantity': line['quantity'],
                'variant_id': line['variant_id'],
                'variant_title': line['variant_title']
            })

        l.product_id = products_map.get(int(order.order_id))
        l.save()
