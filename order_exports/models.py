import json

from django.db import models

from leadgalaxy.models import ShopifyStore


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
    ("authorized", "Only authorized orders"),
    ("pending", "Only pending orders"),
    ("paid", "Only paid orders"),
    ("partially_paid", "Only partially paid orders"),
    ("refunded", "Only refunded orders"),
    ("voided", "Only voided orders"),
    ("partially_refunded", "Only partially_refunded orders"),
    ("any", "All authorized, pending, and paid orders."),
    ("unpaid", "All authorized, or partially_paid orders."),
)


DEFAULT_FIELDS = ('name', 'total_price', 'email')


DEFAULT_FIELDS_CHOICES = (
    ('name', 'Order ID'), ('total_price', 'Total Price'),
    ('email', 'E-mail')
)


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


class OrderExportFilter(models.Model):
    vendor = models.CharField(max_length=255, default="")
    status = models.CharField(max_length=50, default="", blank=True)
    fulfillment_status = models.CharField(max_length=50, default="", blank=True)
    financial_status = models.CharField(max_length=50, default="", blank=True)


class OrderExport(models.Model):
    RELATED_CHOICES = {
        'fields': ORDER_FIELD_CHOICES, 
        'line_fields': ORDER_LINE_FIELD_CHOICES,
        'shipping_address': ORDER_SHIPPING_ADDRESS_CHOICES
    }

    store = models.ForeignKey(ShopifyStore)
    filters = models.OneToOneField(OrderExportFilter)
    created_at = models.DateTimeField(auto_now_add=True)
    schedule = models.TimeField()
    receiver = models.EmailField()
    description = models.CharField(max_length=255, default="")
    url = models.CharField(max_length=512, blank=True, default='')
    sample_url = models.CharField(max_length=512, blank=True, default='')
    since_id = models.CharField(max_length=100, null=True)

    fields = models.TextField(blank=True, default='[]')
    line_fields = models.TextField(blank=True, default='[]')
    shipping_address = models.TextField(blank=True, default='[]')

    def __getattr__(self, name):
        display_list = ['fields_display', 'line_fields_display', 'shipping_address_display']
        if 'display' in name and name in display_list:
            attr = name.replace('_display', '')
            return self.get_data(attr)

        data_list = ['fields_data', 'line_fields_data', 'shipping_address_data']
        if 'data' in name and name in data_list:
            attr = name.replace('_data', '')
            value = getattr(self, attr)
            return json.loads(value)

        choices_list = ['fields_choices', 'line_fields_choices', 'shipping_address_choices']
        if 'choices' in name and name in choices_list:
            attr = name.replace('_choices', '')
            return self.get_selected_choices(attr)

        super(OrderExport, self).__getattr__(name)

    def get_data(self, attr):
        data = json.loads(getattr(self, attr))
        choices = dict(self.RELATED_CHOICES[attr])
        result = []

        for field in data:
            if field in choices:
                result.append(choices[field])

        return result

    def get_selected_choices(self, attr):
        data = json.loads(getattr(self, attr))
        choices = dict(self.RELATED_CHOICES[attr])
        result = []

        for field in data:
            if field in choices:
                result.append([field, choices[field]])

        return result


