# -*- coding: utf-8 -*-
import json
import re
import uuid

from django.contrib.auth.models import User
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver, Signal
from django.utils.functional import cached_property

from leadgalaxy.models import ShopifyStore
from order_exports.api import ShopifyOrderExportAPI


order_export_done = Signal(providing_args=["instance"])


ORDER_STATUS = (
    ("any", "Any order status"),
    ("open", "All open orders"),
    ("closed", "Only closed orders"),
    ("cancelled", "Only cancelled orders"),
)


ORDER_FULFILLMENT_STATUS = (
    ("any", "Orders with any fulfillment_status."),
    ("shipped", "Orders that have been shipped"),
    ("partial", "Partially shipped orders"),
    ("unshipped", "Orders that have not yet been shipped"),
)


ORDER_FINANCIAL_STATUS = (
    ("any", "All authorized, pending, and paid orders."),
    ("authorized", "Only authorized orders"),
    ("pending", "Only pending orders"),
    ("paid", "Only paid orders"),
    ("partially_paid", "Only partially paid orders"),
    ("refunded", "Only refunded orders"),
    ("voided", "Only voided orders"),
    ("partially_refunded", "Only partially_refunded orders"),
    ("unpaid", "All authorized, or partially_paid orders."),
)


DEFAULT_FIELDS = ('name',)
DEFAULT_FIELDS_CHOICES = (('name', 'Order ID'),)


DEFAULT_SHIPPING_ADDRESS = ('name', 'address1', 'address2', 'city', 'zip', 'province',
    'prone', 'country')
DEFAULT_SHIPPING_ADDRESS_CHOICES = (("name", "Name"), ("address1", "Address Line 1"), 
    ("address2", "Address Line 2"), ("city", "City"), ("zip", "ZIP"), 
    ("province", "Province"), ("phone", "Phone"), ("country", "Country"))


DEFAULT_LINE_FIELDS = ('title', 'variant_title', 'sku', 'quantity')
DEFAULT_LINE_FIELDS_CHOICES = (('title', 'Title'), ('variant_title', 'Variant Title'),
    ('sku', 'SKU'), ('quantity', 'Quantity'))


ORDER_FIELD_CHOICES = (('browser_ip', 'Browser IP'),
    ('buyer_accepts_marketing', 'Buyer Accepts Marketing'), ('cart_token', 'Cart Token'),
    ('cancel_reason', 'Cancel Reason'), ('cancelled_at', 'Cancelled At'),
    ('client_details', 'Client Details'), ('closed_at', 'Closed At'), 
    ('created_at', 'Created At'), ('currency', 'Currency'), ('customer', 'Customer'),
    ('discount_codes', 'Discount Codes'), ('email', 'E-mail'), 
    ('financial_status', 'Financial Status'), ('fulfillments', 'Fulfillments'),
    ('fulfillment_status', 'Fulfillment Status'), ('tags', 'Tags'), ('gateway', 'Gateway'),
    ('landing_site', 'Landing Site'), ('name', 'Order ID'), ('note', 'Note'),
    ('note_attributes', 'Note Attributes'), ('payment_gateway_names', 'Payment Gateway Names'),
    ('processed_at', 'Processed At'), ('processing_method', 'Processing Method'),
    ('referring_site', 'Referring Site'), ('refunds', 'Refunds'), 
    ('source_name', 'Source Name'), ('subtotal_price', 'Subtotal Price'), 
    ('taxes_included', 'Taxes Included'), ('token', 'Token'), 
    ('total_discounts', 'Total Discounts'), ('total_line_items_price', 'Total Line Items Price'),
    ('total_price', 'Total Price'), ('total_tax', 'Total Tax'), ('total_weight', 'Total Weight'),
    ('updated_at', 'Updated At'), ('order_status_url', 'Order Status Url')
)


ORDER_LINE_FIELD_CHOICES = (('fulfillable_quantity', 'Fulfillable Quantity'), 
    ('fulfillment_service', 'Fulfillment Service'), ('grams', 'Grams'), 
    ('fulfillment_status', 'Fulfillment Status'), ('vendor', 'Vendor'), 
    ('id', 'ID'), ('price', 'Price'), ('product_id', 'Product ID'), 
    ('quantity', 'Quantity'), ('requires_shipping', 'Requires Shipping'), 
    ('sku', 'SKU'), ('title', 'Title'), ('variant_id', 'Variant ID'), 
    ('variant_title', 'Variant Title'), ('tax_lines', 'Tax Lines'), 
    ('name', 'Name'), ('gift_card', 'Gift Card'), ('properties', 'Properties'), 
    ('taxable', 'Taxable'), ('total_discount', 'Total Discount')
)


ORDER_SHIPPING_ADDRESS_CHOICES = (
    ("address1", "Address Line 1"), ("address2", "Address Line 2"), ("city", "City"),
    ("company", "Company"), ("country", "Country"), ("first_name", "First Name"),
    ("last_name", "Last Name"), ("latitude", "Latitude"), ("longitude", "Longitude"),
    ("phone", "Phone"), ("province", "Province"), ("zip", "ZIP"), ("name", "Name"),
    ("country_code", "Country Code"), ("province_code", "Province Code")
)


def fix_fields(data, choices_list, prefix=''):
    choices_result = []
    data_result = []
    choices = dict(choices_list)

    for field in data:
        field_name = str(field.replace(prefix, ''))
        data_result.append(field_name)
        if field_name in choices:
            choices_result.append([field_name, choices[field_name]])

    return data_result, choices_result


class OrderExportVendor(models.Model):
    owner = models.ForeignKey(User, related_name='vendors')
    user = models.OneToOneField(User, related_name='vendor')
    raw_password = models.CharField(max_length=255, blank=True, null=True)

    def generate_password(self):
        self.raw_password = uuid.uuid4().hex[:6]


def is_vendor(self):
    try:
        return self.vendor is not None
    except OrderExportVendor.DoesNotExist:
        return False


User.add_to_class("is_vendor", cached_property(is_vendor))


class OrderExportFilter(models.Model):
    vendor = models.CharField(max_length=255, default="")
    status = models.CharField(max_length=50, default="", blank=True)
    fulfillment_status = models.CharField(max_length=50, default="", blank=True)
    financial_status = models.CharField(max_length=50, default="", blank=True)
    created_at_min = models.DateTimeField(null=True, blank=True)
    created_at_max = models.DateTimeField(null=True, blank=True)


class OrderExport(models.Model):
    RELATED_CHOICES = {
        'fields': ORDER_FIELD_CHOICES, 
        'line_fields': ORDER_LINE_FIELD_CHOICES,
        'shipping_address': ORDER_SHIPPING_ADDRESS_CHOICES
    }

    store = models.ForeignKey(ShopifyStore)
    filters = models.OneToOneField(OrderExportFilter)
    created_at = models.DateTimeField(auto_now_add=True)
    schedule = models.TimeField(null=True, blank=True)
    receiver = models.TextField(null=True, blank=True)
    description = models.CharField(max_length=255, default="")
    url = models.CharField(max_length=512, blank=True, default='')
    sample_url = models.CharField(max_length=512, blank=True, default='')
    since_id = models.CharField(max_length=100, null=True)
    copy_me = models.BooleanField(default=False)

    previous_day = models.BooleanField(default=True)
    fields = models.TextField(blank=True, default='[]')
    line_fields = models.TextField(blank=True, default='[]')
    shipping_address = models.TextField(blank=True, default='[]')

    progress = models.IntegerField(null=True, blank=True, default=0)
    vendor_user = models.ForeignKey(
        OrderExportVendor, 
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name='exports'
    )

    def __getattr__(self, name):
        display_list = ['fields_display', 'line_fields_display', 'shipping_address_display']
        if 'display' in name and name in display_list:
            attr = name.replace('_display', '')
            return self.get_data(attr)

        data_list = ['fields_data', 'line_fields_data', 'shipping_address_data']
        if 'data' in name and name in data_list:
            attr = name.replace('_data', '')
            value = getattr(self, attr)
            return json.loads(value.replace("'", '"'))

        choices_list = ['fields_choices', 'line_fields_choices', 'shipping_address_choices']
        if 'choices' in name and name in choices_list:
            attr = name.replace('_choices', '')
            return self.get_selected_choices(attr)

        super(OrderExport, self).__getattr__(name)

    @cached_property
    def emails(self):
        SEPARATOR_RE = re.compile(r'[,;]+')
        emails = []
        if self.copy_me:
            emails.append(self.store.user.email)

        for email in SEPARATOR_RE.split(self.receiver):
            emails.append(email.strip(' '))

        return emails

    def send_done_signal(self):
        order_export_done.send(sender=self.__class__, order_export_pk=self.id)

    def get_data(self, attr):
        data = json.loads(getattr(self, attr))
        choices = dict(self.RELATED_CHOICES[attr])
        result = []

        for field in data:
            if field in choices:
                result.append(choices[field])

        return result

    def get_selected_choices(self, attr):
        data = json.loads(getattr(self, attr).replace("'", '"'))
        choices = dict(self.RELATED_CHOICES[attr])
        result = []

        for field in data:
            if field in choices:
                result.append([field, choices[field]])

        return result

    @cached_property
    def query(self):
        return self.queries.first()


class OrderExportQuery(models.Model):
    order_export = models.ForeignKey(OrderExport, related_name="queries")
    created_at = models.DateTimeField(auto_now_add=True) 
    code = models.CharField(max_length=50, null=True, blank=True)
    params = models.TextField(default="")
    count = models.IntegerField(default=0)

    @cached_property
    def params_dict(self):
        return json.loads(self.params)

    class Meta:
        ordering = ['created_at']


class OrderExportLog(models.Model):
    SAMPLE = 'sample'
    COMPLETE = 'complete'
    TYPE_CHOICES = (
        (SAMPLE, 'Sample file'),
        (COMPLETE, 'Complete file')
    )

    started_by = models.DateTimeField(auto_now_add=True)
    finished_by = models.DateTimeField(blank=True, null=True)
    

    order_export = models.ForeignKey(OrderExport, related_name="logs")
    successful = models.BooleanField(default=False)
    csv_url = models.CharField(max_length=512, blank=True, default='')
    type = models.CharField(max_length=100, choices=TYPE_CHOICES, default=SAMPLE)


@receiver(order_export_done)
def generate_reports(sender, order_export_pk, **kwargs):
    from leadgalaxy.tasks import generate_order_export
    order_export = OrderExport.objects.get(pk=order_export_pk)
    order_export.url = ''
    order_export.sample_url = ''
    order_export.progress = 0
    order_export.save()

    if order_export.previous_day:
        api = ShopifyOrderExportAPI(order_export)

        # Generate Sample Export
        api.generate_sample_export()
    else:
        generate_order_export.delay(order_export_pk)

