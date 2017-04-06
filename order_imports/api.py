import csv
import logging
import re
import time

import requests
from raven.contrib.django.raven_compat.models import client as raven_client

from shopified_core.exceptions import ApiProcessException
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

        time.sleep(0.5)
        return response

    def _post_response_from_url(self, url, data):
        """Access any given url and return the corresponding response"""
        # concatenate the URL to be requested with the base url and do the request
        request_url = self.base_url + url
        response = requests.post(request_url, json=data)

        time.sleep(0.5)
        return response

    def _get_order_by_name(self, name=''):
        url = '/admin/orders.json'
        name = ''.join(re.findall(r'[\d]+', name))

        response_json = self._get_response_from_url(url, {'name': name}).json()
        orders = response_json['orders'] if 'orders' in response_json else []
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

    def _send_pusher_notification(self, message, loading=0, finished=False):
        self.store.pusher_trigger('order-import', {
            'finished': finished,
            'store_id': self.store.id,
            'message': message,
            'loading': loading
        })

    def fill_line_items(self, orders={}):
        self._send_pusher_notification('Loading Line Items', 50)
        orders_half_length = len(orders) / 2
        orders_count = 0
        for name in orders:
            orders_count += 1
            order = orders[name]

            if order['shopify'] is not None:
                for line_item in order['shopify']['line_items']:
                    for item in order['items']:
                        if str(line_item['id']) == item['key'] or line_item['sku'] == item['key']:
                            if 'identify' in item and item['identify']:
                                if item['identify'] in line_item['variant_title']:
                                    item['shopify'] = {'id': line_item.get('id')}
                                    break
                            else:
                                item['shopify'] = {'id': line_item.get('id')}
                                break

                # Clean not needed data
                order['shopify'] = {'id': order['shopify'].get('id')}

            # Send notification half way through it to show progress
            if orders_count == orders_half_length:
                self._send_pusher_notification('Loading Line Items', 75)

        return orders

    def find_orders(self, orders={}):
        self._send_pusher_notification('Loading Orders', 20)
        orders_half_length = len(orders) / 2
        orders_count = 0
        for name in orders:
            orders_count += 1
            orders[name]['shopify'] = self._get_order_by_name(name)

            # Send notification half way through it to show progress
            if orders_count == orders_half_length:
                self._send_pusher_notification('Loading Orders', 35)

        return self.fill_line_items(orders)

    def parse_headers(self, csv_file, raw_headers):
        reader = csv.DictReader(csv_file)
        fieldnames = reader.fieldnames

        order_id = raw_headers.get('order_id_position')
        line_item = raw_headers.get('line_item_position')
        tracking_number = raw_headers.get('tracking_number_position')
        identify_column = raw_headers.get('identify_column_position')

        if not order_id:
            name = raw_headers.get('order_id_name')
            if name in fieldnames:
                order_id = fieldnames.index(name)
            else:
                raise ApiProcessException('Not found column of name {} for Order Id #'.format(name))
        else:
            order_id = int(order_id) - 1

        if not line_item:
            name = raw_headers.get('line_item_name')
            if name in fieldnames:
                line_item = fieldnames.index(name)
            else:
                raise ApiProcessException('Not found column of name {} for Line Item ID / Line Item SKU'.format(name))
        else:
            line_item = int(line_item) - 1

        if not tracking_number:
            name = raw_headers.get('tracking_number_name')
            if name in fieldnames:
                tracking_number = fieldnames.index(name)
            else:
                raise ApiProcessException('Not found column of name {} for Tracking Number'.format(name))
        else:
            tracking_number = int(tracking_number) - 1

        headers = {
            'order_id': order_id,
            'line_item': line_item,
            'tracking_number': tracking_number,
        }

        if not identify_column:
            name = raw_headers.get('identify_column_name')
            if name != '' and name in fieldnames:
                identify_column = fieldnames.index(name)
                headers['identify_column'] = identify_column
        else:
            identify_column = int(identify_column) - 1
            headers['identify_column'] = identify_column

        return headers

    def read_csv_file(self, csv_file, headers):
        reader = csv.reader(csv_file)
        orders = {}
        first = True
        for row in reader:
            # Check for empty rows
            if row[0].strip() == '':
                continue

            # Check for fieldnames row
            if first is True:
                first = False
                # Continue if there is no numbers on this row
                row_length = len(row)
                row_items = [row[item] for key, item in headers.items() if item < row_length]
                if all([len(re.findall(r'\d', item)) == 0 for item in row_items]):
                    continue

            data = {
                'key': row[headers.get('line_item')],
                'tracking_number': row[headers.get('tracking_number')],
                'shopify': None
            }

            if headers.get('identify_column') and headers.get('identify_column') < len(row):
                data['identify'] = row[headers.get('identify_column')]

            if row[0] in orders.keys():
                orders[row[headers.get('order_id')]]['items'].append(data)
            else:
                orders[row[headers.get('order_id')]] = {'items': [data], 'shopify': None, 'name': row[0]}

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
