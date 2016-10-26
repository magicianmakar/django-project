import csv
import logging
import tempfile
from os import remove as os_remove
from json import loads, dumps
from datetime import datetime, timedelta
from math import ceil

import requests

from leadgalaxy.utils import aws_s3_upload, send_email_from_template

# Get an instance of a logger
logger = logging.getLogger(__name__)


class ShopifyOrderExportAPI():

    def __init__(self, order_export):
        """Set order_export, store and base url for shopify endpoint URIs"""
        self.order_export = order_export

        # setting ShopifyStore Model for handling the APIs
        self.store = order_export.store

        # create the base url for accessing Shopify with basic http auth
        self.base_url = self.store.get_link('/', api=True)

        self.file_name = tempfile.mktemp(suffix='.csv', prefix='%d-'%self.order_export.id)

    def _get_response_from_url(self, url, params=None):
        """Access any given url and return the corresponding response"""
        # concatenate the URL to be requested with the base url and do the request
        request_url = self.base_url + url
        if params is not None:
            response = requests.get(request_url, params=params)
        else:
            response = requests.get(request_url)

        # check for response and log if error
        if not response.ok:
            logger.error("Error accessing Shopify url %s: \n%s\n Status code: \n%s\n\n RETRYING",
                    response.url, response.text, response.status_code)

            if params is not None:
                response = requests.get(request_url, params=params)
            else:
                response = requests.get(request_url)

        return response

    def _create_url_params(self):
        params = {}
        filters = self.order_export.filters
        for common_status in ['status', 'fulfillment_status', 'financial_status']:
            value = getattr(filters, common_status)
            if value:
                params[common_status] = value

        params['created_at_min'] = self.order_export.created_at.strftime("%Y-%m-%dT%H:%M:%S%z")
        if self.order_export.since_id:
            params['since_id'] = self.order_export.since_id

        return params

    def _get_orders_count(self):
        filters = self._create_url_params()
        url = '/admin/orders/count.json'

        response = self._get_response_from_url(url, filters)

        return response.json()['count']

    def _get_orders(self, limit=250, page=1):
        filters = self._create_url_params()
        url = '/admin/orders.json'

        filters['page'] = page
        filters['limit'] = limit

        response = self._get_response_from_url(url, filters)

        return response.json()['orders']

    def _get_fieldnames(self, selected_choices, prefix=''):
        fieldnames = []
        for field in selected_choices:
            fieldnames.append(prefix + field[1])
        return fieldnames

    def generate_sample_export(self):
        orders = self._get_orders(limit=20)
        url = self.create_csv(orders)

        self.order_export.sample_url = url
        self.order_export.save()

    def generate_export(self):
        count = self._get_orders_count()
        max_pages = ceil(float(count) / 250.0) + 1
        
        orders = []
        for page in range(1, max_pages):
            orders += self._get_orders(page=page)

        url = self.create_csv(orders)

        if len(orders) > 1:
            self.order_export.since_id = orders[-1]['id']

        self.order_export.url = url
        self.order_export.save()

        self.send_email()

    def create_csv(self, orders=[]):
        url = ''
        vendor = self.order_export.filters.vendor

        with open(self.file_name, 'w') as csv_file:
            fields = self.order_export.fields_choices
            fieldnames = self._get_fieldnames(fields)

            line_fields = self.order_export.line_fields_choices
            fieldnames += self._get_fieldnames(line_fields, 'Line Field - ')

            shipping_address = self.order_export.shipping_address_choices
            fieldnames += self._get_fieldnames(shipping_address, 'Shipping Address - ')

            writer = csv.DictWriter(csv_file, fieldnames=fieldnames)

            writer.writeheader()
            for order in orders:
                if vendor.strip() != '':
                    vendor_found = [l for l in order['line_items'] if l['vendor'] == vendor]
                    if len(vendor_found) == 0: # vendor not found on line items
                        continue

                if len(fields):
                    line = {}
                    for field in fields:
                        line[field[1]] = order[field[0]]
                    writer.writerow(line)

                if len(shipping_address) and 'shipping_address' in order:
                    line = {}
                    for field in shipping_address:
                        line['Shipping Address - %s' % field[1]] = order['shipping_address'][field[0]]
                    writer.writerow(line)

                if len(line_fields) and 'line_items' in order:
                    for line_item in order['line_items']:
                        line = {}
                        for line_field in line_fields:
                            line['Line Field - %s' % line_field[1]] = line_item[line_field[0]]
                        writer.writerow(line)

            url = self.send_to_s3(csv_file)
        
        os_remove(self.file_name)

        return url

    def send_to_s3(self, csv_file):
        url = aws_s3_upload(self.file_name, fp=csv_file)

        return url

    def send_email(self):
        data = {
            'url': self.order_export.url
        }

        html_message = send_email_from_template(
            'order_export.html',
            '[Shopified App] Order Export',
            self.order_export.receiver,
            data,
            nl2br=False
        )
