import json
import re

from django.db import models
from django.db.models import Q
from django.urls import reverse
from django.contrib.auth.models import User

from .utils import ALIEXPRESS_SOURCE_STATUS, OrderErrors, safe_str, prefix_from_model, base64_encode


class StoreBase(models.Model):
    class Meta:
        abstract = True

    list_index = models.IntegerField(default=0)
    currency_format = models.CharField(max_length=512, blank=True, null=True)

    def get_url(self, name):
        prefix = prefix_from_model(self)
        if prefix and prefix != 'shopify':
            url = reverse(f'{prefix}:{name}')
        else:
            url = reverse(name)

        return f'{url}?store={self.id}'

    def get_page_url(self, url_name):
        return self.get_url(url_name)


class SupplierBase(models.Model):
    class Meta:
        abstract = True


class ProductBase(models.Model):
    class Meta:
        abstract = True

    def get_bundle_mapping(self, variant=None, default=[]):
        try:
            bundle_map = json.loads(self.bundle_map)
        except:
            bundle_map = {}

        if variant is None:
            return bundle_map
        else:
            return bundle_map.get(str(variant), default)

    def set_bundle_mapping(self, mapping):
        bundle_map = self.get_bundle_mapping()
        bundle_map.update(mapping)

        self.bundle_map = json.dumps(bundle_map)


class BoardBase(models.Model):
    class Meta:
        abstract = True
        ordering = ['title']

    title = models.CharField(max_length=512, blank=True, default='')
    user = models.ForeignKey(User, on_delete=models.CASCADE)

    config = models.CharField(max_length=512, blank=True, default='')
    favorite = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Submission date')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Last update')

    def saved_count(self):
        products = self.products.filter(Q(store__is_active=True) | Q(store__isnull=True))
        products = products.filter(source_id=0)

        return products.count()

    def connected_count(self):
        return self.products.filter(store__is_active=True).exclude(source_id=0).count()


class OrderTrackBase(models.Model):
    class Meta:
        abstract = True
        ordering = ['-created_at']
        index_together = ['store', 'order_id', 'line_id']

    CUSTOM_TRACKING_KEY = 'aftership_domain'

    user = models.ForeignKey(User, on_delete=models.CASCADE)

    order_id = models.BigIntegerField()
    line_id = models.BigIntegerField()

    source_id = models.CharField(max_length=512, blank=True, default='', db_index=True, verbose_name="Source Order ID")
    source_status = models.CharField(max_length=128, blank=True, default='', verbose_name="Source Order Status")
    source_tracking = models.CharField(max_length=128, blank=True, default='', verbose_name="Source Tracking Number")
    source_status_details = models.CharField(max_length=512, blank=True, null=True, verbose_name="Source Status Details")
    source_type = models.CharField(max_length=512, blank=True, null=True, verbose_name="Source Type")

    hidden = models.BooleanField(default=False)
    seen = models.BooleanField(default=False, verbose_name='User viewed the changes')
    auto_fulfilled = models.BooleanField(default=False, verbose_name='Automatically fulfilled')
    check_count = models.IntegerField(default=0)

    data = models.TextField(blank=True, default='')
    errors = models.IntegerField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Submission date')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Last update')
    status_updated_at = models.DateTimeField(auto_now_add=True, verbose_name='Last Status Update')

    def save(self, *args, **kwargs):
        try:
            data = json.loads(self.data)
        except:
            data = None

        if data:
            if data.get('bundle'):
                status = []
                source_tracking = []
                end_reasons = []

                for key, val in list(data.get('bundle').items()):
                    if val.get('source_status'):
                        status.append(val.get('source_status'))

                    if val.get('source_tracking'):
                        source_tracking.append(val.get('source_tracking'))

                    if val.get('end_reason'):
                        end_reasons.append(val.get('end_reason'))

                self.source_status = ','.join(status)
                self.source_tracking = ','.join(source_tracking)
                self.source_status_details = ','.join(end_reasons)

            else:
                self.source_status_details = json.loads(self.data)['aliexpress']['end_reason']

        if self.source_id:
            source_id = str(self.source_id).strip(' ,')
            if ',' in source_id:
                source_id = [i.strip() for i in list(filter(len, re.split('[, ]+', self.source_id)))]
                source_id = ','.join(source_id)

            if self.source_id != source_id:
                self.source_id = source_id

        super().save(*args, **kwargs)

    def encoded(self):
        return base64_encode(json.dumps(self.data))

    def get_source_status_details(self):
        if self.source_status_details and ',' in self.source_status_details:
            source_status_details = []
            for i in self.source_status_details.split(','):
                source_status_details.append(ALIEXPRESS_SOURCE_STATUS.get(safe_str(i).lower()))

            return ', '.join(set(source_status_details))
        else:
            return ALIEXPRESS_SOURCE_STATUS.get(safe_str(self.source_status_details).lower())

    def get_source_status_color(self):
        if not self.source_status:
            return 'danger'
        elif self.source_status == 'FINISH':
            return 'primary'
        else:
            return 'warning'

    def get_source_ids(self):
        if self.source_id:
            return ', '.join(set(['#{}'.format(i) for i in self.source_id.split(',')]))

    def get_source_url(self):
        if self.source_id:
            if self.source_type == 'ebay':
                return 'https://vod.ebay.com/vod/FetchOrderDetails?purchaseOrderId={}'.format(self.source_id)
            if self.source_type == 'other':
                return ''
            else:
                return 'http://trade.aliexpress.com/order_detail.htm?orderId={}'.format(self.source_id)
        else:
            return None

    def get_source_status(self):
        status_map = {
            # Aliexpress
            "PLACE_ORDER_SUCCESS": "Awaiting Payment",
            "IN_CANCEL": "Awaiting Cancellation",
            "WAIT_SELLER_SEND_GOODS": "Awaiting Shipment",
            "SELLER_PART_SEND_GOODS": "Partial Shipment",
            "WAIT_BUYER_ACCEPT_GOODS": "Awaiting delivery",
            "WAIT_GROUP_SUCCESS": "Pending operation success",
            "FINISH": "Order Completed",
            "IN_ISSUE": "Dispute Orders",
            "IN_FROZEN": "Frozen Orders",
            "WAIT_SELLER_EXAMINE_MONEY": "Payment not yet confirmed",
            "RISK_CONTROL": "Payment being verified",
            "IN_PRESELL_PROMOTION": "Promotion is on",
            "FUND_PROCESSING": "Fund Processing",

            # eBay
            "BUYER_NO_SHOW": "Pickup cancelled buyer no show",
            "BUYER_REJECTED": "Pickup cancelled buyer rejected",
            "DELIVERED": "Delivered",
            "DIRECT_DEBIT": "Direct Debit",
            "EXTERNAL_WALLET": "Processed by PayPal",
            "IN_TRANSIT": "In transit",
            "MANIFEST": "Shipping Info Received",
            "NO_PICKUP_INSTRUCTIONS_AVAILABLE": "No pickup instruction available",
            "NOT_PAID": "Not Paid",
            "NOT_SHIPPED": "Item is not shipped",
            "SHIPPED": "Shipped",
            "OUT_OF_STOCK": "Out of stock",
            "PENDING_MERCHANT_CONFIRMATION": "Order is being prepared",
            "PICKED_UP": "Picked up",
            "PICKUP_CANCELLED_BUYER_NO_SHOW": "Pickup cancelled buyer no show",
            "PICKUP_CANCELLED_BUYER_REJECTED": "Pickup cancelled buyer rejected",
            "PICKUP_CANCELLED_OUT_OF_STOCK": "Out of stock",
            "READY_FOR_PICKUP": "Ready for pickup",
            "SHIPPING_INFO_RECEIVED": "Shipping info received"
        }

        if self.source_status and ',' in self.source_status:
            source_status = []
            for i in self.source_status.split(','):
                if status_map.get(i, ''):
                    source_status.append(status_map.get(i, ''))

            return ', '.join(set(source_status))

        else:
            return status_map.get(self.source_status, '')

    def get_tracking_link(self):
        custom_tracking = 'http://track.aftership.com/{{tracking_number}}'

        if type(self.user.get_config(self.CUSTOM_TRACKING_KEY)) is dict:
            custom_tracking = self.user.get_config(self.CUSTOM_TRACKING_KEY).get(str(self.store_id), custom_tracking)

            if '{{tracking_number}}' not in custom_tracking:
                custom_tracking = "http://{}.aftership.com/{{{{tracking_number}}}}".format(custom_tracking)
            elif not custom_tracking.startswith('http'):
                custom_tracking = 'http://{}'.format(re.sub('^([:/]*)', r'', custom_tracking))

        if self.source_tracking:
            if ',' in self.source_tracking:
                urls = []
                for tracking in self.source_tracking.split(','):
                    urls.append([tracking, custom_tracking.replace('{{tracking_number}}', tracking)])

                return urls
            else:
                return custom_tracking.replace('{{tracking_number}}', self.source_tracking)

    def add_error(self, error, commit=False):
        try:
            data = json.loads(self.data)
        except:
            data = {}

        if 'errors' not in data:
            data['errors'] = []

        if error in data['errors']:
            return

        data['errors'].append(error)

        self.data = json.dumps(data)

        if commit:
            self.commit()

    def get_errors(self):
        errors = []

        if self.errors > 0:
            if self.errors & OrderErrors.NAME:
                errors.append('Customer Name')

            if self.errors & OrderErrors.CITY:
                errors.append('City')

            if self.errors & OrderErrors.COUNTRY:
                errors.append('Country')

        return errors

    def clear_errors(self, commit=False):
        try:
            data = json.loads(self.data)
        except:
            data = {}

        if 'errors' in data:
            del data['errors']

            self.data = json.dumps(data)

            if commit:
                self.commit()

    def get_errors_details(self):
        try:
            data = json.loads(self.data)
        except:
            data = {}

        return list(set(data.get('errors', [])))

    get_source_status.admin_order_field = 'source_status'


class UserUploadBase(models.Model):
    class Meta:
        abstract = True
        ordering = ['-created_at']

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    url = models.CharField(max_length=512, blank=True, default='', verbose_name="Upload file URL")

    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Submission date')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Last update')

    def __str__(self):
        return f'<UserUploadBase: {self.id}>'
