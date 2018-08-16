from leadgalaxy.models import ShopifyOrderTrack
from commercehq_core.models import CommerceHQOrderTrack


def get_shopify_order_data(store, data):
    customer = data.get('customer', {})
    customer_name = u'{} {}'.format(customer.get('first_name', ''), customer.get('last_name', '')).strip()
    billing_address = data.get('billing_address', {})
    shipping_address = data.get('shipping_address', {})
    line_items = []

    tracks = {}
    for track in ShopifyOrderTrack.objects.filter(store=store, order_id=data.get('id')):
        tracks[str(track.line_id)] = {
            'source_id': track.source_id,
            'source_type': track.source_type,
            'source_status': track.source_status,
            'source_tracking': track.source_tracking,
        }

    for i, item in enumerate(data.get('line_items', [])):
        track = tracks.get(str(item['id']), {})
        item = {
            'title': item['title'],
            'name': item['name'],
            'vendor': item['vendor'],
            'variant_title': item['variant_title'],
            'sku': item['sku'],
            'quantity': item['quantity'],
            'price': item['price'],

            # source tracking
            'source_id': '',
            'source_type': '',
            'source_status': '',
            'source_tracking': '',
        }
        item.update(track)
        line_items.append(item)

    return {
        'store_id': store.id,
        'store_title': store.title,

        'billing_address': billing_address,
        'shipping_address': shipping_address,

        'created_at': data.get('created_at', None),
        'closed_at': data.get('closed_at', None),
        'cancelled_at': data.get('cancelled_at', None),

        'customer_name': customer_name,
        'customer_email': customer.get('email', ''),
        'customer_phone': customer.get('phone', ''),

        'financial_status': data.get('financial_status', ''),
        'fulfillment_status': data.get('fulfillment_status', ''),

        'line_items': line_items,

        'note': data.get('note', ''),
        'order_no': data.get('id'),
        'order_name': data.get('name', None),
        'subtotal_price': data.get('subtotal_price', None),
        'total_tax': data.get('total_tax', None),
        'total_price': data.get('total_price', None),
    }


def get_chq_order_data(store, data):
    customer = data.get('customer', {})
    customer_name = u'{} {}'.format(customer.get('first_name', ''), customer.get('last_name', '')).strip()
    address = data.get('address', {})
    billing_address = address.get('billing', {})
    shipping_address = address.get('shipping', {})
    line_items = []

    tracks = {}
    for track in CommerceHQOrderTrack.objects.filter(store=store, order_id=data.get('id')):
        tracks[str(track.line_id)] = {
            'source_id': track.source_id,
            'source_type': track.source_type,
            'source_status': track.source_status,
            'source_tracking': track.source_tracking,
        }

    for i, item in enumerate(data.get('items', [])):
        track = tracks.get(str(item['data']['id']), {})
        variant = item['data'].get('variant', {})
        variant = variant.get('variant', [])
        item = {
            'title': item['data']['title'],
            'name': item['data']['title'],
            'vendor': item['data']['vendor'],
            'variant_title': ' / '.join(variant),
            'sku': item['data']['sku'],
            'quantity': item['status']['quantity'],
            'price': item['data']['price'],

            # source tracking
            'source_id': '',
            'source_type': '',
            'source_status': '',
            'source_tracking': '',
        }
        item.update(track)
        line_items.append(item)

    order_status = {
        0: 'Not sent to fulfilment',
        1: 'Partially sent to fulfilment',
        2: 'Partially sent to fulfilment & shipped',
        3: 'Sent to fulfilment',
        4: 'Partially shipped',
        5: 'Shipped',
    }

    paid_status = {
        0: 'Not paid',
        1: 'Paid',
        -1: 'Partially refunded',
        -2: 'Fully refunded',
    }

    return {
        'store_id': store.id,
        'store_title': store.title,

        'billing_address': billing_address,
        'shipping_address': shipping_address,

        'created_at': data.get('order_date'),
        'closed_at': None,
        'cancelled_at': None,

        'customer_name': customer_name,
        'customer_email': customer.get('email', ''),
        'customer_phone': address.get('phone', ''),

        'financial_status': paid_status.get(data['paid']),
        'fulfillment_status': order_status.get(data['status']),

        'line_items': line_items,

        'note': data.get('notes', ''),
        'order_no': data.get('id'),
        'order_name': data.get('display_number', None),
        'subtotal_price': None,
        'total_tax': data.get('tax', None),
        'total_price': data.get('total', None),
    }
