import json
from urllib.parse import urlencode

import requests
from django.core.cache import cache

from shopified_core.utils import base64_encode, hash_text
from supplements.models import ShipStationAccount


class LimitExceededError(Exception):
    def __init__(self, *args, **kwargs):
        self.retry_after = kwargs.pop('retry_after') or 0
        super().__init__(*args, **kwargs)


def get_auth_header(shipstation_acc):
    api_key = shipstation_acc.api_key
    api_secret = shipstation_acc.api_secret

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


def prepare_shipping_data(order):
    ship_to = json.dumps(order['shipping_address'], sort_keys=True)
    try:
        bill_to = json.dumps(order['billing_address'])
        if not order['billing_address']['address1'].strip():
            raise KeyError('address1')
    except KeyError:
        bill_to = ship_to

    return [ship_to, bill_to]


def create_shipstation_order(pls_order, shipstation_acc, raw_request=False):
    headers = {'Content-Type': 'application/json'}
    headers.update(get_auth_header(shipstation_acc))
    shipstation_url = shipstation_acc.api_url
    url = f'{shipstation_url}/orders/createOrder'
    data = pls_order.to_shipstation_order()
    r = requests.post(url, data=json.dumps(data), headers=headers)

    if r.status_code == 429:
        retry_after = r.headers.get('Retry-After', 0)
        if not retry_after:
            # Shipstation has a custom header posing as Retry-After of HTTP 429
            retry_after = r.headers.get('X-Rate-Limit-Reset', 0)

        raise LimitExceededError(retry_after=retry_after)

    r.raise_for_status()
    result = r.json()

    if not result.get('orderKey'):
        raise Exception('Error returning order key from shipstation')

    pls_order.shipstation_key = result['orderKey']
    pls_order.save()


def get_orders_lock(token=None):
    lock = cache.lock('create_shipstation_orders_lock', timeout=60)

    if token:
        lock.local.token = token.encode() if isinstance(token, str) else token

    if lock.owned():
        lock.reacquire()
        return lock

    if lock.acquire(blocking=False):
        return lock

    return False


def send_shipstation_orders():
    from supplements.tasks import create_shipstation_orders

    lock = get_orders_lock()
    if lock:
        create_shipstation_orders.delay(lock.local.token)

        return True

    return False


def get_shipstation_order(order_number, shipstation_acc):
    headers = {'Content-Type': 'application/json'}
    headers.update(get_auth_header(shipstation_acc))
    url = f'{shipstation_acc.api_url}/orders'

    response = requests.get(url, params={'orderNumber': order_number}, headers=headers)
    response.raise_for_status()
    result = response.json()
    if isinstance(result, dict) and 'orders' in result:
        result = result['orders'][0] if len(result['orders']) > 0 else {}
    return result


def get_shipstation_shipments(resource_url, shipstation_acc=None):
    headers = {'Content-Type': 'application/json'}
    headers.update(get_auth_header(shipstation_acc))
    resource_url = f'{resource_url}?pageSize=500'
    response = requests.get(resource_url, headers=headers).json()

    shipments = get_paginated_response(response, resource_url, 'shipments', shipstation_acc)

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

    data = response[key]
    total_pages = response['pages']
    next_page = 2
    while next_page <= total_pages:
        url = f'{url}&page={next_page}'
        response = requests.get(url, headers=headers).json()
        data = data + response[key]
        next_page += 1

    return data
