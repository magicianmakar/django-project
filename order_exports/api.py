# -*- coding: utf-8 -*-
import csv
import logging
import tempfile
import os
import uuid
import simplejson as json
from math import ceil

import requests
from django.core.urlresolvers import reverse
from django.utils import timezone
from django.utils.text import slugify
from raven.contrib.django.raven_compat.models import client as raven_client

from leadgalaxy.utils import aws_s3_upload, order_track_fulfillment
from shopified_core.utils import send_email_from_template


# Get an instance of a logger
logger = logging.getLogger(__name__)
GENERATED_PAGE_LIMIT = 10


class ShopifyOrderExportAPI():

    def __init__(self, order_export, code=None):
        """Set order_export, store and base url for shopify endpoint URIs"""
        self.order_export = order_export

        self.unique_code = code
        if self.unique_code:
            self.query = order_export.queries.get(code=self.unique_code)
        else:
            self.query = order_export.query

        # setting ShopifyStore Model for handling the APIs
        self.store = order_export.store

        # create the base url for accessing Shopify with basic http auth
        self.base_url = self.store.get_link('/', api=True)
        self.file_path = tempfile.mktemp(suffix='.csv', prefix='export_%d_' % self.order_export.id)

        file_name = self.file_path.split('/')[-1]
        self._s3_path = os.path.join('order-exports', str(self.order_export.id), file_name)

        self.order_export.save()

        raven_client.user_context({
            'id': self.store.user.id,
            'username': self.store.user.username,
            'email': self.store.user.email
        })

    def _get_response_from_url(self, url, params=None):
        request_url = self.base_url + url
        return requests.get(request_url, params=params)

    def _post_response_from_url(self, url, data):
        request_url = self.base_url + url
        return requests.post(request_url, json=data)

    def _put_response_from_url(self, url, data):
        request_url = self.base_url + url
        return requests.put(request_url, json=data)

    def _create_fulfillment_params(self, order_id, tracking_number, line_item_id):
        data = order_track_fulfillment(**{
            'order_id': order_id,
            'line_id': line_item_id,
            'source_tracking': tracking_number,
            'user_config': self.store.user.get_config()
        })

        return data

    def _post_fulfillment(self, data, order_id, fulfillment_id):
        if fulfillment_id:
            url = '/admin/orders/{}/fulfillments/{}.json'.format(order_id, fulfillment_id)
            data['fulfillment']['id'] = fulfillment_id
            response = self._put_response_from_url(url=url, data=data)
        else:
            url = '/admin/orders/{}/fulfillments.json'.format(order_id)
            response = self._post_response_from_url(url=url, data=data)

        return response.ok

    def _create_url_params(self):
        params = {}
        filters = self.order_export.filters
        for common_status in ['status', 'fulfillment_status', 'financial_status']:
            value = getattr(filters, common_status)
            if value:
                params[common_status] = value

        if self.order_export.previous_day:
            if self.order_export.starting_at:
                params['created_at_min'] = self.order_export.starting_at.strftime("%Y-%m-%dT%H:%M:%S%z")
            else:
                params['created_at_min'] = self.order_export.created_at.strftime("%Y-%m-%dT%H:%M:%S%z")

            if self.order_export.since_id:
                params['since_id'] = self.order_export.since_id
        else:
            params['created_at_min'] = self.order_export.filters.created_at_min.strftime("%Y-%m-%dT%H:%M:%S%z")
            params['created_at_max'] = self.order_export.filters.created_at_max.strftime("%Y-%m-%dT%H:%M:%S%z")

        ids = self.order_export.get_orders_id_from_product_search()
        if ids is not None:
            params['ids'] = ids

        return params

    def _get_orders_count(self, params):
        url = '/admin/orders/count.json'

        response = self._get_response_from_url(url, params)

        return response.json()['count']

    def _get_orders(self, params={}, limit=250, page=1):
        url = '/admin/orders.json'

        params['page'] = page
        params['limit'] = limit

        response = self._get_response_from_url(url, params)

        return response.json()['orders']

    def _get_fieldnames(self, selected_choices, prefix=''):
        fieldnames = []
        for field in selected_choices:
            fieldnames.append(prefix + field[1])
        return fieldnames

    def _percentage(self, current_page, max_pages):
        return (max_pages / current_page) * 95

    @property
    def _get_unique_code(self):
        if self.unique_code:
            return self.unique_code

        count = 1
        while count != 0:
            self.unique_code = uuid.uuid4().hex[:6].upper()
            count = self.order_export.queries.filter(code=self.unique_code).count()

        return self.unique_code

    def fulfill(self, order_id, tracking_number, line_item_id, fulfillment_id=''):
        fulfillment_params = self._create_fulfillment_params(order_id, tracking_number, line_item_id)

        return self._post_fulfillment(fulfillment_params, order_id, fulfillment_id)

    def generate_query(self, send_email=True):
        if self.order_export.previous_day:
            params = self._create_url_params()
            self.query = self.order_export.queries.create(
                params=json.dumps(params),
                code=self._get_unique_code,
                count=self._get_orders_count(params)
            )

            if send_email:
                # Only check for orders if an e-mail should be sent
                orders = self._get_orders(params=self.query.params_dict, page=1, limit=1)
                if len(orders) > 0:
                    self.send_email(code=self._get_unique_code)

    def generate_sample_export(self):
        log = self.order_export.logs.create()
        try:
            params = self._create_url_params()
            orders = self._get_orders(params=params, limit=20)
            url = self.create_csv(orders)

            self.order_export.sample_url = url
            self.order_export.save()

            log.successful = True
            log.finished_by = timezone.now()
            log.csv_url = url
            log.type = log.SAMPLE
            log.save()

        except Exception:
            raven_client.captureException()
            log.finished_by = timezone.now()
            log.save()

    def generate_export(self):
        log = self.order_export.logs.create()

        try:
            params = self._create_url_params()

            count = self._get_orders_count(params)
            max_pages = int(ceil(float(count) / 250.0) + 1)

            orders = []
            for page in range(1, max_pages):
                if not self.order_export.previous_day:
                    self.order_export.progress = self._percentage(page, max_pages)
                    self.order_export.save()
                orders += self._get_orders(params=params, page=page)

            url = self.create_csv(orders)

            if len(orders) > 1:
                self.order_export.since_id = orders[-1]['id']

            self.order_export.progress = 100
            self.order_export.url = url
            self.order_export.save()

            log.successful = True
            log.finished_by = timezone.now()
            log.csv_url = url
            log.type = log.COMPLETE
            log.save()

        except Exception:
            raven_client.captureException()
            log.finished_by = timezone.now()
            log.save()

    def get_query_info(self):
        count = self._get_orders_count(params=self.query.params_dict)
        max_pages = int(ceil(float(count) / float(GENERATED_PAGE_LIMIT)) + 1)

        return {
            'fieldnames': {
                'fields': self.order_export.fields_choices,
                'shipping_address': self.order_export.shipping_address_choices,
                'line_items': self.order_export.line_fields_choices,
            },
            'pages': range(1, max_pages),
            'max_page': max_pages - 1,
            'count': count
        }

    def get_data(self, page=1):
        if not self.query:
            return []

        orders = self._get_orders(params=self.query.params_dict, page=page, limit=GENERATED_PAGE_LIMIT)
        vendor = slugify(self.order_export.filters.vendor.strip())

        fields = self.order_export.fields_choices
        line_fields = self.order_export.line_fields_choices
        shipping_address = self.order_export.shipping_address_choices

        lines = []
        for order in orders:
            line = {'fields': {}, 'shipping_address': {}, 'line_items': []}
            if vendor != '':
                vendor_found = [l for l in order['line_items'] if l['vendor'] == vendor]
                if len(vendor_found) == 0:  # vendor not found on line items
                    continue

            line['fields']['id'] = unicode(order['id']).encode("utf-8")

            if len(fields):
                for field in fields:
                    line['fields'][field[0]] = unicode(order[field[0]]).encode("utf-8")

            if len(shipping_address) and 'shipping_address' in order:
                for field in shipping_address:
                    line['shipping_address'][field[0]] = unicode(order['shipping_address'][field[0]]).encode("utf-8")

            if len(line_fields) and 'line_items' in order:
                for line_item in order['line_items']:
                    if vendor.strip() != '' and slugify(line_item['vendor']) != vendor:
                        continue

                    items = {}
                    for line_field in line_fields:
                        items[line_field[0]] = unicode(line_item[line_field[0]]).encode("utf-8")

                    items['id'] = line_item['id']
                    for fulfillment in order['fulfillments']:
                        for line_item in fulfillment['line_items']:
                            if items['id'] == line_item['id']:
                                items['tracking_number'] = fulfillment.get('tracking_number') or ''
                                items['fulfillment_id'] = fulfillment['id']
                                break

                        if items.get('tracking_number'):
                            break

                    line['line_items'].append(items)

            lines.append(line)

        return lines

    def create_csv(self, orders=[]):
        url = ''
        vendor = slugify(self.order_export.filters.vendor.strip())

        with open(self.file_path, 'wr') as csv_file:
            fields = self.order_export.fields_choices
            fieldnames = self._get_fieldnames(fields)

            line_fields = self.order_export.line_fields_choices
            fieldnames += self._get_fieldnames(line_fields, 'Line Field - ')

            shipping_address = self.order_export.shipping_address_choices
            fieldnames += self._get_fieldnames(shipping_address, 'Shipping Address - ')

            writer = csv.DictWriter(csv_file, fieldnames=fieldnames)

            writer.writeheader()
            for order in orders:
                if vendor != '':
                    vendor_found = [l for l in order['line_items'] if slugify(l['vendor']) == vendor]
                    if len(vendor_found) == 0:  # vendor not found on line items
                        continue

                line = {}
                if len(fields):
                    write = True
                    for field in fields:
                        line[field[1]] = unicode(order[field[0]]).encode("utf-8")

                if len(shipping_address) and 'shipping_address' in order:
                    write = True
                    for field in shipping_address:
                        line['Shipping Address - %s' % field[1]] = unicode(order['shipping_address'][field[0]]).encode("utf-8")

                if write:
                    writer.writerow(line)

                if len(line_fields) and 'line_items' in order:
                    for line_item in order['line_items']:
                        if vendor != '' and slugify(line_item['vendor']) != vendor:
                            continue

                        line = {}
                        for line_field in line_fields:
                            line['Line Field - %s' % line_field[1]] = unicode(line_item[line_field[0]]).encode("utf-8")
                        writer.writerow(line)

        url = self.send_to_s3()

        return url

    def send_to_s3(self):
        url = aws_s3_upload(self._s3_path, input_filename=self.file_path)

        os.remove(self.file_path)

        return url

    def send_email(self, code):
        data = {
            'url': 'https://app.shopifiedapp.com{}'.format(reverse('order_exports_generated', kwargs={
                'order_export_id': self.order_export.id, 'code': code
            }))
        }

        send_email_from_template(
            tpl='order_export.html',
            subject='[Shopified App] Order Export',
            recipient=self.order_export.emails,
            data=data,
            nl2br=False
        )
