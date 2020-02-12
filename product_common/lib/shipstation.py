import json

from django.conf import settings

import requests

from shopified_core.utils import base64_encode


def get_auth_header():
    api_key = settings.SHIPSTATION_API_KEY
    api_secret = settings.SHIPSTATION_API_SECRET

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
    headers.update(get_auth_header())
    url = f'{settings.SHIPSTATION_API_URL}/orders/createOrder'
    response = requests.post(url, data=json.dumps(data), headers=headers)
    response = response.json()

    pls_order.shipstation_key = response['orderKey']
    pls_order.save()


def get_shipstation_shipments(resource_url):
    headers = {'Content-Type': 'application/json'}
    headers.update(get_auth_header())
    response = requests.get(resource_url, headers=headers)
    data = response.json()
    return data['shipments']
