import json
from urllib.parse import urlencode

from django.conf import settings

import requests

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
        'name': store_data['name'],
        'company': store_data.get('company', ''),
        'street1': store_data['address1'],
        'street2': store_data.get('address2', ''),
        'city': store_data['city'],
        'state': store_data['province'],
        'postalCode': store_data['zip'],
        'country': store_data['country_code'],
        'phone': store_data['phone'],
    }
    if hashed:
        ship_to = hash_text(json.dumps(ship_to, sort_keys=True))

    return ship_to


def prepare_shipstation_data(pls_order, order, line_items):
    ship_to = get_address(order['shipping_address'])
    try:
        bill_to = get_address(order['billing_address'])
    except KeyError:
        bill_to = ship_to

    hash = hash_text(json.dumps(ship_to, sort_keys=True))
    pls_order.shipping_address_hash = hash
    pls_order.save()

    get_shipstation_line_key = PLSOrderLine.get_shipstation_key

    items = []
    for item in line_items:
        quantity = item['quantity']
        items.append({
            'name': item['title'],
            'quantity': quantity,
            'sku': item['sku'],
            'unitPrice': float(item['user_supplement'].cost_price),
            'imageUrl': item.get('image_url', ''),
        })

        label = item['label']

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

    return {
        'orderNumber': pls_order.shipstation_order_number,
        'orderDate': pls_order.created_at.strftime('%Y-%m-%dT%H:%M:%S%z'),
        'orderStatus': 'awaiting_shipment',
        'amountPaid': pls_order.amount / 100.,
        'shipTo': ship_to,
        'billTo': bill_to,
        'items': items,
        'advancedOptions': advancedOptions,
    }


def create_shipstation_order(pls_order, data):
    headers = {'Content-Type': 'application/json'}
    headers.update(get_auth_header())
    url = f'{settings.SHIPSTATION_API_URL}/orders/createOrder'
    response = requests.post(url, data=json.dumps(data), headers=headers)
    response.raise_for_status()
    response = response.json()

    pls_order.shipstation_key = response['orderKey']
    pls_order.save()


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
