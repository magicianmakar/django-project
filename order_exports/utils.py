import csv
import logging
import os
import re
import simplejson as json
import tempfile
import uuid
from math import ceil

import arrow
import requests
from django.db.models.query_utils import Q
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify
from lib.exceptions import capture_exception, capture_message

from shopified_core.utils import app_link, send_email_from_template, clean_query_id
from leadgalaxy.utils import aws_s3_upload, order_track_fulfillment
from leadgalaxy.shopify import ShopifyAPI
from leadgalaxy.models import ShopifyOrderTrack, User, ShopifyStore
from shopify_orders import utils as shopify_orders_utils


# Get an instance of a logger
logger = logging.getLogger(__name__)
GENERATED_PAGE_LIMIT = 10


class ShopifyOrderExport():

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
        self.file_path = tempfile.mktemp(suffix='.csv', prefix='export_%d_' % self.order_export.id)

        file_name = self.file_path.split('/')[-1]
        self._s3_path = os.path.join('order-exports', str(self.order_export.id), file_name)

        self.order_export.save()

        # raven_client.user_context({'id': self.store.user.id, 'username': self.store.user.username, 'email': self.store.user.email})

    def _get_response_from_url(self, url, params=None):
        request_url = self.store.api(url)
        return requests.get(request_url, params=params)

    def _post_response_from_url(self, url, data):
        request_url = self.store.api(url)
        return requests.post(request_url, json=data)

    def _put_response_from_url(self, url, data):
        request_url = self.store.api(url)
        return requests.put(request_url, json=data)

    def _create_fulfillment_params(self, order_id, tracking_number, line_item_id):
        data = order_track_fulfillment(**{
            'order_id': order_id,
            'line_id': line_item_id,
            'source_tracking': tracking_number,
            'user_config': self.store.user.get_config(),
            'location_id': self.store.get_primary_location()
        })

        return data

    def _post_fulfillment(self, data, order_id, fulfillment_id):
        raise NotImplementedError

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

    def _get_orders(self, params=None, limit=250, page=1):
        if params is None:
            params = {}

        url = '/admin/orders.json'

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

            self.save_generated_export_order_ids()

            if send_email:
                # Only check for orders if an e-mail should be sent
                orders = self._get_orders(params=self.query.params_dict, page=1, limit=1)
                if len(orders) > 0:
                    self.send_email(code=self._get_unique_code)

    def generate_sample_export(self):
        log = self.order_export.logs.create()
        log.type = log.SAMPLE

        try:
            params = self._create_url_params()
            orders = self._get_orders(params=params, limit=20)
            url = self.create_csv(orders)

            self.order_export.sample_url = url
            self.order_export.save()

            log.successful = True
            log.finished_by = timezone.now()
            log.csv_url = url

        except Exception:
            capture_exception()

            log.successful = False
            log.finished_by = timezone.now()

        finally:
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
            capture_exception()
            log.finished_by = timezone.now()
            log.save()

    def get_query_info(self, limit=GENERATED_PAGE_LIMIT):
        if self.query.found_order_ids:
            count = self._get_orders_count(params={'ids': self.query.found_order_ids})
            max_pages = int(ceil(float(count) / float(limit)) + 1)
        else:
            count = 0
            max_pages = 1

        return {
            'fieldnames': {
                'fields': self.order_export.fields_choices,
                'shipping_address': self.order_export.shipping_address_choices,
                'line_items': self.order_export.line_fields_choices,
            },
            'pages': list(range(1, max_pages)),
            'max_page': max_pages - 1,
            'count': count
        }

    def get_data(self, page=1, limit=GENERATED_PAGE_LIMIT):
        raise NotImplementedError

    def create_csv(self, orders=None):
        if orders is None:
            orders = []

        vendor = slugify(self.order_export.filters.vendor.strip())

        with open(self.file_path, 'w') as csv_file:
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
                    vendor_found = [o_line for o_line in order['line_items'] if slugify(o_line['vendor']) == vendor]
                    if len(vendor_found) == 0:  # vendor not found on line items
                        continue

                line = {}
                if len(fields):
                    write = True
                    for field in fields:
                        line[field[1]] = str(order[field[0]])

                if len(shipping_address) and 'shipping_address' in order:
                    write = True
                    for field in shipping_address:
                        line['Shipping Address - %s' % field[1]] = str(order['shipping_address'][field[0]])

                if write:
                    writer.writerow(line)

                if len(line_fields) and 'line_items' in order:
                    for line_item in order['line_items']:
                        if vendor != '' and slugify(line_item['vendor']) != vendor:
                            continue

                        line = {}
                        for line_field in line_fields:
                            line['Line Field - %s' % line_field[1]] = str(line_item[line_field[0]])
                        writer.writerow(line)

        url = self.send_to_s3()

        return url

    def send_to_s3(self):
        url = aws_s3_upload(self._s3_path, input_filename=self.file_path)

        os.remove(self.file_path)

        return url

    def send_email(self, code):
        data = {
            'url': app_link(reverse('order_exports_generated', kwargs={
                'order_export_id': self.order_export.id, 'code': code
            }))
        }

        send_email_from_template(
            tpl='order_export.html',
            subject='[Dropified] Order Export',
            recipient=self.order_export.emails,
            data=data
        )

    def save_generated_export_order_ids(self):
        count = self._get_orders_count(self.query.params_dict)
        max_pages = int(ceil(float(count) / 250.0) + 1)

        vendor_no_spaces = re.sub(r'\s+', '.*?', self.order_export.filters.vendor.lower())
        vendor_compiled = re.compile(vendor_no_spaces, re.I)

        order_ids = []
        vendors = []

        for page in range(1, max_pages):
            orders = self._get_orders(params=self.query.params_dict, page=page, limit=250)
            for order in orders:
                for order_line_item in order['line_items']:
                    # Filter by vendor only if needed
                    if self.order_export.filters.vendor != '':
                        # Only process when vendor name exists
                        vendor_name = order_line_item.get('vendor', '') or ''
                        if vendor_name != '':
                            # Found vendor
                            if vendor_compiled.search(vendor_name) is not None:
                                order_ids.append(str(order['id']))

                                if vendor_name not in vendors:
                                    vendors.append(vendor_name)

                                break  # Leave loop on line_items
                    else:
                        # Get all order ids and vendor names
                        order_ids.append(str(order['id']))
                        vendor_name = order_line_item.get('vendor', '') or ''

                        if vendor_name != '' and vendor_name not in vendors:
                            vendors.append(vendor_name)

        self.query.found_order_ids = ','.join(order_ids)
        self.query.found_vendors = ', '.join(vendors)
        self.query.save()


class ShopifyTrackOrderExport():

    def __init__(self, store):
        self.store = ShopifyStore.objects.get(id=store)
        # create the base url for accessing Shopify with basic http auth
        self.file_path = tempfile.mktemp(suffix='.csv', prefix='order_export_')

        file_name = self.file_path.split('/')[-1]
        self._s3_path = os.path.join('order-exports', file_name)

    def generate_tracked_export(self, params):
        self.user = User.objects.get(id=params["user_id"])

        orders = ShopifyOrderTrack.objects.filter(user=self.user, store=self.store).defer('data')

        if params.get('date'):
            date = params['date']
        else:
            date = arrow.get(timezone.now()).replace(days=-30).format('MM/DD/YYYY-')

        if params["query"]:
            date = None

        created_at_start, created_at_end = None, None
        if date:
            try:
                daterange_list = date.split('-')

                tz = timezone.localtime(timezone.now()).strftime(' %z')

                created_at_start = arrow.get(daterange_list[0] + tz, r'MM/DD/YYYY Z').datetime

                if len(daterange_list) > 1 and daterange_list[1]:
                    created_at_end = arrow.get(daterange_list[1] + tz, r'MM/DD/YYYY Z')
                    created_at_end = created_at_end.span('day')[1].datetime

            except:
                capture_exception(level='warning')

        if params["query"]:
            order_id = shopify_orders_utils.order_id_from_name(self.store, params["query"])

            if order_id:
                orders = orders.filter(order_id=order_id)
            else:
                orders = orders.filter(Q(source_id=clean_query_id(params["query"]))
                                       | Q(source_tracking=params["query"]))

        if params["tracking"] == '0':
            orders = orders.filter(source_tracking='')
        elif params["tracking"] == '1':
            orders = orders.exclude(source_tracking='')

        if params["fulfillment"] == '1':
            orders = orders.filter(shopify_status='fulfilled')
        elif params["fulfillment"] == '0':
            orders = orders.exclude(shopify_status='fulfilled')

        if params["hidden"] == '1':
            orders = orders.filter(hidden=True)
        elif not params["hidden"] or params["hidden"] == '0':
            orders = orders.exclude(hidden=True)

        if params["reason"]:
            if params["reason"].startswith('_'):
                orders = orders.filter(source_status=params["reason"][1:])
            else:
                orders = orders.filter(source_status_details=params["reason"])

        if created_at_start:
            orders = orders.filter(created_at__gte=created_at_start)

        if created_at_end:
            orders = orders.filter(created_at__lte=created_at_end)

        params['date_from'] = created_at_start
        params['date_to'] = created_at_end

        capture_message('Order Track Export', extra=params)

        self.create_track_orders_csv(orders, params)

    def create_track_orders_csv(self, orders, params):
        orders_count = orders.count()

        email_data = {
            'url': None,
            'date_from': params['date_from'],
            'date_to': params['date_to'],
            'count': orders_count,
            'user': self.user,
        }

        if not orders_count:
            return self.send_email(email_data)
        elif orders_count > 1000:
            capture_message("Exporting a lot of orders", extra=params)

        start = 0
        steps = 200

        api = ShopifyAPI(self.store)
        with open(self.file_path, 'w') as csv_file:
            fieldnames = ['Shopify Order', 'Shopify Item', 'Shopify Product Title', 'Supplier Order ID', 'Tracking Number']
            writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
            writer.writeheader()

            while start <= orders_count:
                orders_chunk = orders[start:start + steps]
                orders_ids = list(set([o.order_id for o in orders_chunk]))

                shopify_orders = {}
                for orders_page in api.paginate_orders(ids=orders_ids, fields='id,name,line_items'):
                    for order in orders_page:
                        shopify_orders[order['id']] = order

                for order in orders_chunk:
                    shopify_order = shopify_orders.get(order.order_id)
                    if not shopify_order:
                        continue

                    # Match the Order line id by looping through all line items to get variant title
                    order_title = ''
                    for items in shopify_order['line_items']:
                        if items['id'] == order.line_id:
                            order_title = items['name']
                            break

                    writer.writerow({
                        'Shopify Order': shopify_order['name'] if shopify_order else order.order_id,
                        'Shopify Item': order.line_id,
                        'Shopify Product Title': order_title,
                        'Supplier Order ID': order.source_id,
                        'Tracking Number': f'="{order.source_tracking}"' if order.source_tracking else '',  # excel formula to format value as text,
                    })

                start += steps

        email_data['url'] = self.send_to_s3()

        self.send_email(email_data)

    def send_to_s3(self):
        url = aws_s3_upload(self._s3_path, input_filename=self.file_path)
        os.remove(self.file_path)

        return url

    def send_email(self, data):
        send_email_from_template(
            tpl='tracked_order_export.html',
            subject='[Dropified] Tracking Numbers Export',
            recipient=self.user.email,
            data=data
        )
