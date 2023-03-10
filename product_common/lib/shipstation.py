import json
from urllib.parse import urlencode

import requests

from shopified_core.utils import base64_encode
from supplements.models import ShipStationAccount


def get_auth_header(shipstation_acc):
    api_key = shipstation_acc.api_key
    api_secret = shipstation_acc.api_secret

    content = f"{api_key}:{api_secret}"
    encoded = base64_encode(content)
    return {'Authorization': f'Basic {encoded}'}


def get_address(store_data):
    return {
        'name': store_data['name'],
        'company': store_data['company'],
        'street1': store_data['address1'],
        'street2': store_data['address2'],
        'city': store_data['city'],
        'state': store_data['province'],
        'postalCode': store_data['zip'],
        'country': store_data['country_code'],
        'phone': store_data['phone'],
    }


def prepare_shipstation_data(pls_order, order, line_items):
    ship_to = get_address(order['shipping_address'])
    try:
        bill_to = get_address(order['billing_address'])
    except KeyError:
        bill_to = ship_to

    items = []
    for item in line_items:
        items.append({
            'name': item['title'],
            'quantity': item['quantity'],
            'sku': item['sku'],
            'unitPrice': item['price'],
        })

    return {
        'orderNumber': order['order_number'],
        'orderDate': order['created_at'],
        'amountPaid': pls_order.amount / 100.,
        'shipTo': ship_to,
        'billTo': bill_to,
        'items': items,
    }


def create_shipstation_order(pls_order, raw_data):
    data = {
        'orderNumber': raw_data['orderNumber'],
        'orderDate': raw_data['orderDate'],
        'orderStatus': 'awaiting_shipment',
        'billTo': raw_data['billTo'],
        'shipTo': raw_data['shipTo'],
        'amountPaid': raw_data['amountPaid'],
        'items': raw_data['items'],
    }

    headers = {'Content-Type': 'application/json'}
    shipstation_acc = pls_order.label.user_supplement.pl_supplement.shipstation_account
    headers.update(get_auth_header(shipstation_acc))
    shipstation_url = shipstation_acc.api_url
    url = f'{shipstation_url}/orders/createOrder'
    response = requests.post(url, data=json.dumps(data), headers=headers)
    response = response.json()

    pls_order.shipstation_key = response['orderKey']
    pls_order.save()


def get_shipstation_shipments(resource_url):
    shipstation_accounts = ShipStationAccount.objects.all()
    shipments = []
    for shipstation_acc in shipstation_accounts:
        headers = {'Content-Type': 'application/json'}
        headers.update(get_auth_header(shipstation_acc))
        if resource_url.endswith('?'):
            resource_url = f'{resource_url}pageSize=500'
        elif resource_url.find('?') > -1:
            resource_url = f'{resource_url}&pageSize=500'
        else:
            resource_url = f'{resource_url}?pageSize=500'

        response = requests.get(resource_url, headers=headers).json()
        shipments = get_paginated_response(response, resource_url, 'shipments', shipstation_acc)
        if shipments:
            break

    return shipments


def get_shipstation_orders(params=None):
    shipstation_accounts = ShipStationAccount.objects.all()
    orders = []
    for shipstation_acc in shipstation_accounts:
        shipstation_url = shipstation_acc.api_url
        resource_url = f'{shipstation_url}/orders?pageSize=500'
        if params:
            resource_url = '{}&{}'.format(resource_url, urlencode(params))

        headers = {'Content-Type': 'application/json'}
        headers.update(get_auth_header(shipstation_acc))
        response = requests.get(resource_url, headers=headers).json()
        acc_orders = get_paginated_response(response, resource_url, 'orders', shipstation_acc)

        for acc_order in acc_orders:
            orders.append(acc_order)
    return orders


def get_paginated_response(response, url, key, shipstation_acc):
    headers = {'Content-Type': 'application/json'}
    headers.update(get_auth_header(shipstation_acc))

    data = response.get(key, [])
    total_pages = response.get('pages', 1)
    next_page = 2
    while next_page <= total_pages:
        url = f'{url}&page={next_page}'
        response = requests.get(url, headers=headers).json()
        data = data + response[key]
        next_page += 1

    return data
