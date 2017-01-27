import csv
import logging
import re

import requests
from raven.contrib.django.raven_compat.models import client as raven_client

from leadgalaxy.utils import order_track_fulfillment

# Get an instance of a logger
logger = logging.getLogger(__name__)


class ShopifyOrderImportAPI():
    MAX_ORDERS_PER_PAGE = 250

    def __init__(self, store=None):
        """Set store and base url for shopify orders endpoint URLs.

            Keyword arguments:
            store -- instance of leadgalaxy.models.ShopifyStore (default None)
        """
        self.store = store

        if self.store is None:
            raise Exception("Store not set.")

        # Sets the base url for accessing Shopify api endpoint.
        self.base_url = self.store.get_link(api=True)

        raven_client.user_context({
            'id': self.store.user.id,
            'username': self.store.user.username,
            'email': self.store.user.email
        })

    def _get_response_from_url(self, url, params=None):
        """Access any given url and return the corresponding response"""
        # concatenate the URL to be requested with the base url and do the request
        request_url = self.base_url + url
        if params is not None:
            response = requests.get(request_url, params=params)
        else:
            response = requests.get(request_url)

        return response

    def _post_response_from_url(self, url, data):
        """Access any given url and return the corresponding response"""
        # concatenate the URL to be requested with the base url and do the request
        request_url = self.base_url + url
        response = requests.post(request_url, json=data)

        return response

    def _get_order_by_name(self, name=''):
        url = '/admin/orders.json'
        name = ''.join(re.findall(r'[\d]+', name))

        response = self._get_response_from_url(url, {'name': name})
        orders = response.json()['orders']
        orders_count = len(orders)

        if orders_count == 1:
            return orders[0]
        elif orders_count > 1:
            # Search for an order with exact name
            search = '#' + name
            for order in orders:
                if search == order['name']:
                    return order

        return None

    def fill_line_items(self, orders={}):
        for name in orders:
            order = orders[name]
            if order['shopify'] is not None:
                for line_item in order['shopify']['line_items']:
                    for item in order['items']:
                        if str(line_item['id']) == item['key'] or line_item['sku'] == item['key']:
                            item['shopify'] = line_item
                            break
        return orders

    def find_orders(self, orders={}):
        for name in orders:
            orders[name]['shopify'] = self._get_order_by_name(name)

        return self.fill_line_items(orders)

    def read_csv_file(self, csv_file):
        reader = csv.reader(csv_file)
        orders = {}
        first = True
        for row in reader:
            # Check for fieldnames row
            if first is True:
                first = False
                # Continue if there is no numbers on this row
                if not all([re.findall('\d', item) is None for item in row]):
                    continue

            data = {'key': row[1], 'tracking_number': row[2], 'shopify': None}
            if row[0] in orders:
                orders[row[0]]['items'].append(data)
            else:
                orders[row[0]] = {'items': [data], 'shopify': None, 'name': row[0]}

        return orders

    def parse_csv(self, csv_file):
        parsed_orders = self.read_csv_file(csv_file)

        orders = self.find_orders(parsed_orders)

        return orders

    def send_tracking_number(self, items):
        tracking = {}
        success = True
        for item in items:
            key = '{}-{}'.format(item['order_id'], item['tracking_number'])
            if key in tracking:
                tracking[key]['fulfillment']['line_items'].append({'id': item['line_item_id']})
            else:
                data = order_track_fulfillment(**{
                    'order_id': item['order_id'],
                    'line_id': item['line_item_id'],
                    'source_tracking': item['tracking_number'],
                    'user_config': self.store.user.get_config()
                })
                tracking[key] = data

        for key, data in tracking.iteritems():
            order_id = key.split('-')[0]
            url = '/admin/orders/{}/fulfillments.json'.format(order_id)
            response = self._post_response_from_url(url, data)
            if not response.ok:
                success = False

        return success
