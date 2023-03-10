import json
import re

import arrow
from django.contrib.auth.models import User
from django.contrib.postgres.fields import ArrayField
from django.db import models
from django.db.models import Q
from django.urls import reverse, Resolver404, resolve
from django.utils.functional import cached_property

from shopified_core.utils import get_domain, add_http_schema
from supplements.models import SUPPLEMENTS_SUPPLIER, UserSupplement
from .utils import ALIEXPRESS_SOURCE_STATUS, OrderErrors, safe_str, prefix_from_model, base64_encode


class StoreBase(models.Model):
    class Meta:
        abstract = True

    list_index = models.IntegerField(default=0)
    currency_format = models.CharField(max_length=512, blank=True, null=True)

    @property
    def currency_format_with_default(self):
        return self.currency_format or '${{amount}}'

    @property
    def store_type(self):
        return prefix_from_model(self)

    @property
    def store_type_key(self):
        return f"{self.store_type}_{self.id}"

    def get_url(self, name, **kwargs):
        prefix = self.store_type
        if prefix and prefix != 'shopify':
            url = reverse(f'{prefix}:{name}')
        else:
            url = reverse(name)

        params = f"&{'&'.join(kwargs)}" if kwargs else ''
        return f'{url}?store={self.id}{params}'

    def get_page_url(self, url_name):
        return self.get_url(url_name)


class SupplierBase(models.Model):
    class Meta:
        abstract = True

    @property
    def is_dropified(self):
        return 'dropified.com' in self.product_url \
               or 'shopifytools-pr-' in self.product_url \
               or self.supplier_name == 'Dropified'

    @property
    def is_dropified_print(self):
        return self.supplier_type() == 'dropified-print'

    @property
    def is_pls(self):
        try:
            return bool(
                (self.is_dropified and 'supplement' in self.product_url)
                or safe_str(self.supplier_name) in SUPPLEMENTS_SUPPLIER
            )
        except:
            return False

    @property
    def is_logistics(self):
        return self.supplier_type() == 'logistics'

    @property
    def is_alibaba(self):
        return self.supplier_type() == 'alibaba'

    @property
    def is_walmart(self):
        return self.supplier_type() == 'walmart'

    @property
    def is_supplement_deleted(self):
        if not self.user_supplement:
            return True

        return self.user_supplement.is_supplement_deleted

    @property
    def is_label_approved(self):
        if not self.user_supplement:
            return False

        return self.user_supplement.is_approved

    @cached_property
    def user_supplement(self):
        if self.is_pls:
            try:
                user_supplement_id = self.get_user_supplement_id()
                return UserSupplement.objects.get(id=user_supplement_id)
            except UserSupplement.DoesNotExist:
                return None

    def get_user_supplement_id(self):
        # https://app.dropified.com/supplements/usersupplement/{id}
        product_url = '/'.join(self.product_url.split('/')[3:])
        try:
            resolved = resolve(f'/{product_url}')
            url_pattern = f"{resolved.namespace}:{resolved.url_name}"
            if url_pattern == 'pls:user_supplement':
                return resolved.kwargs['supplement_id']

        except Resolver404:
            # TODO: catch this to make sure supplier uses supplement url
            return None

    def supplier_type(self):
        try:
            if self.is_dropified and 'print-on-demand' in self.product_url:
                return 'dropified-print'
            if self.is_dropified and 'logistics' in self.product_url:
                return 'logistics'
            if self.is_pls:
                return 'pls'

            return get_domain(self.product_url)
        except:
            return ''


class ProductBase(models.Model):
    class Meta:
        abstract = True

    user = models.ForeignKey(User, on_delete=models.CASCADE)

    title = models.TextField(blank=True, null=True, db_index=True)
    price = models.FloatField(default=0.0)
    product_type = models.CharField(max_length=255, blank=True, default='')
    tags = models.TextField(blank=True, null=True, default='')
    boards_list = ArrayField(models.IntegerField(), null=True, blank=True)

    data = models.TextField(default='{}', null=True, blank=True)
    notes = models.TextField(null=True, blank=True)

    config = models.TextField(null=True, blank=True)
    variants_map = models.TextField(default='', blank=True)
    supplier_map = models.TextField(default='', null=True, blank=True)
    shipping_map = models.TextField(default='', null=True, blank=True)
    bundle_map = models.TextField(null=True, blank=True)
    mapping_config = models.TextField(null=True, blank=True)

    monitor_id = models.IntegerField(null=True)

    user_supplement = models.ForeignKey(UserSupplement, null=True, on_delete=models.SET_NULL)

    master_product = models.ForeignKey('multichannel_products_core.MasterProduct', on_delete=models.SET_NULL, null=True, blank=True)
    master_variants_map = models.TextField(blank=True, null=True, default='{}')

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    def get_bundle_mapping(self, variant=None, default=None):
        try:
            bundle_map = json.loads(self.bundle_map)
        except:
            bundle_map = {}

        if variant is None:
            return bundle_map
        else:
            if default is None:
                default = []

            return bundle_map.get(str(variant), default)

    def set_bundle_mapping(self, mapping):
        bundle_map = self.get_bundle_mapping()
        bundle_map.update(mapping)

        self.bundle_map = json.dumps(bundle_map)

    def get_real_variant_id(self, variant_id):
        """
        Used to get current variant id from previously delete variant id
        """

        config = self.get_config()
        if config.get('real_variant_map'):
            return config.get('real_variant_map').get(str(variant_id), variant_id)

        return variant_id

    def to_json(self):
        try:
            data = json.loads(self.data)
        except:
            data = {}

        return {
            'id': self.id,
            'title': self.title,
            'price': self.price,
            'product_type': self.product_type,
            'notes': self.notes,
            'tags': self.tags,
            'data': data,
            'created_at': arrow.get(self.created_at).timestamp,
        }

    def from_json(self, product_data):
        self.title = product_data['title']
        self.price = product_data['price']
        self.product_type = product_data['product_type']
        self.notes = product_data['notes']

        self.tags = product_data['tags']

        self.data = json.dumps(product_data['data'])

        self.created_at = arrow.get(product_data['created_at']).timestamp


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
                if re.match(r'\d{2}-\d{5}-\d{5}', self.source_id) and self.created_at < arrow.get('2022-02-01').datetime:
                    return f'https://order.ebay.com/ord/show?orderId={self.source_id}&purchaseOrderId={self.source_id}#/'
                else:
                    return f'https://order.ebay.com/ord/show?/ViewPaymentStatus&purchaseOrderId={self.source_id}'
            elif self.source_type == 'other':
                return ''
            elif self.source_type == 'supplements':
                return f"{reverse('pls:my_orders')}?transaction_id={self.source_id}"
            elif self.source_type == 'dropified-print':
                return f"{reverse('prints:orders')}?order={self.source_id}"
            elif self.source_type == 'alibaba':
                return f'https://biz.alibaba.com/ta/detail.htm?orderId={self.source_id}'
            elif self.source_type == 'dropified-logistics':
                return reverse('logistics:order', kwargs={'order_id': self.source_id})
            else:
                return 'https://trade.aliexpress.com/order_detail.htm?orderId={}'.format(self.source_id)
        else:
            return None

    def get_source_name(self):
        if self.source_type == 'ebay':
            return 'eBay'
        elif self.source_type == 'other':
            return 'Custom'
        elif self.source_type == 'supplements':
            return 'Private Label'
        elif self.source_type == 'dropified-print':
            return 'Print on Demand'
        elif self.source_type == 'alibaba':
            return 'Alibaba'
        elif self.source_type == 'dropified-logistics':
            return '3PL'
        else:
            return 'Aliexpress'

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
            "SHIPPING_INFO_RECEIVED": "Shipping info received",

            # Dropified
            "D_PENDING_PAYMENT": "Pending Payment",
            "D_PAID": "Confirmed Payment",
            "D_PENDING_SHIPMENT": "Pending Shipment",
            "D_SHIPPED": "Shipped",

            # Alibaba
            "ALIBABA_to_be_audited": "High risk order, awaiting manual review",
            "ALIBABA_unpay": "Awaiting Payment",
            "ALIBABA_paying": "Verifying payment",
            "ALIBABA_payment_failed": "Payment Failed",
            "ALIBABA_undeliver": "Pending Shipment",
            "ALIBABA_delivering": "Shipped",
            "ALIBABA_wait_confirm_receipt": "Waiting delivery confirmation",
            "ALIBABA_frozen": "Under Dispute",
            "ALIBABA_charge_back": "Refunded",
            "ALIBABA_trade_close": "Closed",
            "ALIBABA_trade_success": "Order Completed",
        }

        if self.source_status and ',' in self.source_status:
            source_status = []
            for i in self.source_status.split(','):
                if status_map.get(i, ''):
                    source_status.append(status_map.get(i, ''))

            return ', '.join(set(source_status))

        else:
            return status_map.get(self.source_status, '')

    @cached_property
    def custom_tracking_url(self):
        custom_tracking = self.user.get_config(self.CUSTOM_TRACKING_KEY)
        if type(custom_tracking) is dict:
            return custom_tracking.get(str(self.store_id), 'https://track.aftership.com/{{tracking_number}}')
        return None

    def get_tracking_link(self):
        custom_tracking = self.custom_tracking_url or 'https://track.aftership.com/{{tracking_number}}'

        if self.source_type == 'alibaba':
            from alibaba_core.utils import get_tracking_links as get_alibaba_tracking_links
            links = get_alibaba_tracking_links(self.source_id.split(','), custom_tracking)
            if links:
                return links

        if self.custom_tracking_url:
            if '{{tracking_number}}' not in custom_tracking:
                custom_tracking = "https://{}.aftership.com/{{{{tracking_number}}}}".format(custom_tracking)
            elif not custom_tracking.startswith('http'):
                custom_tracking = 'http://{}'.format(re.sub('^([:/]*)', r'', custom_tracking))

            custom_tracking = add_http_schema(custom_tracking)

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


class OrdersSyncStatusAbstract(models.Model):
    class Meta:
        abstract = True

    SYNC_STATUS = (
        (0, 'Pending'),
        (1, 'Started'),
        (2, 'Completed'),
        (3, 'Unauthorized'),
        (4, 'Error'),
        (5, 'Disabled'),
        (6, 'Reset'),
    )

    sync_type = models.CharField(max_length=32)
    sync_status = models.IntegerField(default=0, choices=SYNC_STATUS)
    orders_count = models.IntegerField(default=0)
    pending_orders = models.TextField(blank=True, null=True)
    revision = models.IntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    elastic = models.BooleanField(default=False)

    def __str__(self):
        return '{} / {}'.format(self.sync_type, self.store.title)

    def add_pending_order(self, order_id, commit=True):
        try:
            pending_orders = self.pending_orders.split(',')
        except:
            pending_orders = []

        order_id = str(order_id)
        if order_id not in pending_orders:
            pending_orders.append(order_id)
            self.pending_orders = ','.join(pending_orders)

            if commit:
                self.save()

    def pop_pending_orders(self, commit=True):
        try:
            pending_orders = self.pending_orders.split(',')
        except:
            pending_orders = []

        if len(pending_orders):
            order = pending_orders.pop()
            self.pending_orders = ','.join(pending_orders)
        else:
            order = None

        if commit:
            self.save()

        return order
