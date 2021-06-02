import json
from urllib.parse import urlencode

from django.conf import settings

import requests

from lib.exceptions import capture_message
from shopified_core.utils import base64_encode, hash_text
from supplements.models import PLSOrderLine


def get_auth_header():
    api_key = settings.SHIPSTATION_API_KEY
    api_secret = settings.SHIPSTATION_API_SECRET

    content = f"{api_key}:{api_secret}"
    encoded = base64_encode(content)
    return {'Authorization': f'Basic {encoded}'}


def get_address(store_data, hashed=False):
    ship_to = {
        'name': store_data['name'] or '',
        'company': store_data.get('company') or '',
        'street1': store_data['address1'] or '',
        'street2': store_data.get('address2') or '',
        'city': store_data['city'] or '',
        'state': store_data['province'] or '',
        'postalCode': store_data['zip'] or '',
        'country': store_data['country_code'] or '',
        'phone': store_data['phone'] or '',
    }
    if hashed:
        ship_to = hash_text(json.dumps(ship_to, sort_keys=True))

    return ship_to


def prepare_shipstation_data(pls_order, order, line_items, service_code=None):
    ship_to = get_address(order['shipping_address'])
    try:
        bill_to = get_address(order['billing_address'])
        if not bill_to['address1'].strip():
            raise KeyError('address1')
    except KeyError:
        bill_to = ship_to

    hash = hash_text(json.dumps(ship_to, sort_keys=True))
    pls_order.shipping_address_hash = hash
    pls_order.save()

    get_shipstation_line_key = PLSOrderLine.get_shipstation_key

    items = []
    for item in line_items:
        label = item['label']
        quantity = item['quantity']
        items.append({
            'name': item['title'] or label.user_supplement.title,  # Shipstation name is required
            'quantity': quantity,
            'sku': item['sku'],
            'unitPrice': float(item['user_supplement'].cost_price),
            'imageUrl': item.get('image_url', ''),
        })

        key = get_shipstation_line_key(pls_order.store_type,
                                       pls_order.store_id,
                                       pls_order.store_order_id,
                                       item['id'],
                                       label.id)

        items.append({
            'name': f'Label for {label.user_supplement.title}',
            'quantity': quantity,
            'sku': label.sku,
            'unitPrice': 0,
            'imageUrl': label.url,
            'lineItemKey': key,
        })

    advancedOptions = {
        'customField1': order['order_number'],
    }

    if pls_order.is_taxes_paid:
        advancedOptions['customField2'] = 'Duties Paid'

    shipping_data = {
        'orderNumber': pls_order.shipstation_order_number,
        'orderDate': pls_order.created_at.strftime('%Y-%m-%dT%H:%M:%S%z'),
        'orderStatus': 'awaiting_shipment',
        'amountPaid': pls_order.amount / 100.,
        'shipTo': ship_to,
        'billTo': bill_to,
        'items': items,
        'advancedOptions': advancedOptions,
    }
    if service_code:
        shipping_data['requestedShippingService'] = service_code

    return shipping_data


def create_shipstation_order(pls_order, data, raw_request=False):
    headers = {'Content-Type': 'application/json'}
    headers.update(get_auth_header())
    url = f'{settings.SHIPSTATION_API_URL}/orders/createOrder'

    if raw_request:
        response = requests.post(url, data=json.dumps(data), headers=headers)
        response.raise_for_status()
        response = response.json()
        if not response.get('orderKey'):
            raise Exception(response)

        return response['orderKey']

    else:
        for i in range(2):
            try:
                response = requests.post(url, data=json.dumps(data), headers=headers)
                response.raise_for_status()
                response = response.json()
                if response.get('orderKey'):
                    break

            except requests.HTTPError:
                pass

            capture_message('ShipStation Order Retry', level='warning', extra={'retry': i + 1, 'data': data})

        if response.get('orderKey'):
            pls_order.shipstation_key = response['orderKey']
            pls_order.save()
        else:
            capture_message('ShipStation Error', extra={'response': response})


def get_shipstation_order(order_number):
    headers = {'Content-Type': 'application/json'}
    headers.update(get_auth_header())
    url = f'{settings.SHIPSTATION_API_URL}/orders'

    response = requests.get(url, params={'orderNumber': order_number}, headers=headers)
    response.raise_for_status()
    result = response.json()
    if isinstance(result, dict) and 'orders' in result:
        result = result['orders'][0] if len(result['orders']) > 0 else {}
    return result


def get_shipstation_shipments(resource_url):
    headers = {'Content-Type': 'application/json'}
    headers.update(get_auth_header())
    resource_url = f'{resource_url}?pageSize=500'
    response = requests.get(resource_url, headers=headers).json()

    shipments = get_paginated_response(response, resource_url, 'shipments')

    return shipments


def get_shipstation_orders(params=None):
    resource_url = f'{settings.SHIPSTATION_API_URL}/orders?pageSize=500'
    if params:
        resource_url = '{}&{}'.format(resource_url, urlencode(params))

    headers = {'Content-Type': 'application/json'}
    headers.update(get_auth_header())
    response = requests.get(resource_url, headers=headers).json()

    orders = get_paginated_response(response, resource_url, 'orders')

    return orders


def get_paginated_response(response, url, key):
    headers = {'Content-Type': 'application/json'}
    headers.update(get_auth_header())

    data = response[key]
    total_pages = response['pages']
    next_page = 2
    while next_page <= total_pages:
        url = f'{url}&page={next_page}'
        response = requests.get(url, headers=headers).json()
        data = data + response[key]
        next_page += 1

    return data
