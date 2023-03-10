import simplejson as json
import re
import uuid

from django.contrib.auth.models import User
from django.db import models
from django.dispatch import receiver, Signal
from django.utils.functional import cached_property

from leadgalaxy.models import ShopifyStore
from order_exports.utils import ShopifyOrderExport


order_export_done = Signal(providing_args=["instance"])


# status, text, explanation
ORDER_STATUS = (
    ("open", "All open orders", " for |all open| orders"),
    ("any", "Any order status", " for orders with |any status|"),
    ("closed", "Only closed orders", " for only |closed| orders"),
    ("cancelled", "Only cancelled orders", " for only |cancelled| orders"),
)


ORDER_FULFILLMENT_STATUS = (
    ("unshipped,partial", "Unshipped or partially unshipped", " with |unshipped or partially unshipped| products"),
    ("unshipped", "Orders that have not yet been shipped", " with only |unshipped| products"),
    ("partial", "Partially shipped orders", " with |partially shipped| products"),
    ("shipped", "Orders that have been fulfilled", " with all products |shipped|"),
    ("any", "Orders with any fulfillment status.", ""),
)


ORDER_FINANCIAL_STATUS = (
    ("paid", "Only paid orders", " with |paid| finances"),
    ("any", "All authorized, pending, and paid orders.", ""),
    ("authorized", "Only authorized orders", " with |authorized| finances"),
    ("pending", "Only pending orders", " with |all pending| finances"),
    ("partially_paid", "Only partially paid orders", " with |partially paid| finances"),
    ("refunded", "Only refunded orders", " with |refunded| finances"),
    ("voided", "Only voided orders", " where finances have been |voided|"),
    ("partially_refunded", "Only partially refunded orders", " where finances have been |partially refunded|"),
    ("unpaid", "All authorized, or partially paid orders.", " where orders have |all authorized or partially paid| finances"),
)


DEFAULT_FIELDS = ('name',)
DEFAULT_FIELDS_CHOICES = (('name', 'Order ID'),)


DEFAULT_SHIPPING_ADDRESS = ('name', 'address1', 'address2', 'city', 'zip', 'province',
                            'prone', 'country')
DEFAULT_SHIPPING_ADDRESS_CHOICES = (
    ("name", "Name"), ("address1", "Address Line 1"),
    ("address2", "Address Line 2"), ("city", "City"), ("zip", "ZIP"),
    ("province", "Province"), ("phone", "Phone"), ("country", "Country"))


DEFAULT_LINE_FIELDS = ('title', 'variant_title', 'sku', 'quantity')
DEFAULT_LINE_FIELDS_CHOICES = (('title', 'Title'), ('variant_title', 'Variant Title'),
                               ('sku', 'SKU'), ('quantity', 'Quantity'))


ORDER_FIELD_CHOICES = (
    ('browser_ip', 'Browser IP'),
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


ORDER_LINE_FIELD_CHOICES = (
    ('fulfillable_quantity', 'Fulfillable Quantity'),
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
    owner = models.ForeignKey(User, related_name='owned_vendors', on_delete=models.CASCADE)
    user = models.ForeignKey(User, related_name='vendors', on_delete=models.CASCADE)
    raw_password = models.CharField(max_length=255, blank=True, null=True)

    def generate_password(self):
        self.raw_password = uuid.uuid4().hex[:6]

    def __str__(self):
        return '{} @{}'.format(self.owner, self.user)


def is_vendor(self):
    return self.vendors.exists()


User.add_to_class("is_vendor", cached_property(is_vendor).__set_name__(User, 'is_vendor'))


class OrderExportFilter(models.Model):
    vendor = models.CharField(max_length=255, default="")
    status = models.CharField(max_length=50, default="", blank=True)
    fulfillment_status = models.CharField(max_length=50, default="", blank=True)
    financial_status = models.CharField(max_length=50, default="", blank=True)
    created_at_min = models.DateTimeField(null=True, blank=True)
    created_at_max = models.DateTimeField(null=True, blank=True)
    product_price_min = models.FloatField(null=True, blank=True)
    product_price_max = models.FloatField(null=True, blank=True)
    product_title = models.TextField(blank=True, null=True, default='')

    def __str__(self):
        return '<OrderExportFilter {}>'.format(self.vendor)


class OrderExport(models.Model):
    RELATED_CHOICES = {
        'fields': ORDER_FIELD_CHOICES,
        'line_fields': ORDER_LINE_FIELD_CHOICES,
        'shipping_address': ORDER_SHIPPING_ADDRESS_CHOICES
    }

    store = models.ForeignKey(ShopifyStore, on_delete=models.CASCADE)
    filters = models.OneToOneField(OrderExportFilter, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    schedule = models.TimeField(null=True, blank=True)
    receiver = models.TextField(null=True, blank=True)
    description = models.CharField(max_length=255, default="")
    url = models.CharField(max_length=512, blank=True, default='')
    sample_url = models.CharField(max_length=512, blank=True, default='')
    since_id = models.CharField(max_length=100, null=True)
    copy_me = models.BooleanField(default=False)

    previous_day = models.BooleanField(default=True)
    starting_at = models.DateTimeField(null=True, blank=True)
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

    def __str__(self):
        return '<OrderExport {}>'.format(self.store.title)

    @cached_property
    def emails(self):
        SEPARATOR_RE = re.compile(r'[,;]+')
        emails = []
        if self.copy_me:
            emails.append(self.store.user.email)

        for email in SEPARATOR_RE.split(self.receiver):
            emails.append(email.strip(' '))

        return emails

    @cached_property
    def json_found_products(self):
        products = []
        for found_product in self.found_products.all():
            products.append({
                'image_url': found_product.image_url,
                'title': found_product.title,
                'product_id': found_product.product_id,
            })

        return json.dumps(products)

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

    def get_orders_id_from_product_search(self):
        from shopify_orders.models import ShopifyOrder
        orders = ShopifyOrder.objects.filter(store=self.store)
        search_for_products = False

        if self.filters.product_price_min is not None:
            search_for_products = True
            orders = orders.filter(shopifyorderline__price__gte=self.filters.product_price_min)

        if self.filters.product_price_max is not None:
            search_for_products = True
            orders = orders.filter(shopifyorderline__price__lte=self.filters.product_price_max)

        # Start query for: title OR id
        query = None

        # Search for product titles
        if self.filters.product_title is not None:
            titles = json.loads(self.filters.product_title or '[]')
            if len(titles) > 0:
                search_for_products = True
                query = models.Q(shopifyorderline__title__icontains=titles[0])

                for title in titles[1:]:
                    query = query | models.Q(shopifyorderline__title__icontains=title)

        # Search for shopify exact found products
        if self.found_products.count() > 0:
            search_for_products = True
            found_product_ids = list(self.found_products.values_list('product_id', flat=True))
            if query is None:
                query = models.Q(shopifyorderline__shopify_product__in=found_product_ids)
            else:
                query = query | models.Q(shopifyorderline__shopify_product__in=found_product_ids)

        # Apply query filter for title OR id
        if query is not None:
            orders = orders.filter(query)

        if search_for_products:
            order_ids = list(orders.distinct().values_list('order_id', flat=True))
            return ','.join(str(x) for x in order_ids)
        else:
            return None


class OrderExportFoundProduct(models.Model):
    order_export = models.ForeignKey(OrderExport, related_name='found_products', on_delete=models.CASCADE)
    image_url = models.TextField()
    title = models.TextField()
    product_id = models.BigIntegerField()


class OrderExportQuery(models.Model):
    order_export = models.ForeignKey(OrderExport, related_name="queries", on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    code = models.CharField(max_length=50, null=True, blank=True)
    params = models.TextField(default="")
    count = models.IntegerField(default=0)
    found_order_ids = models.TextField(default='')
    found_vendors = models.TextField(default='')

    @cached_property
    def params_dict(self):
        return json.loads(self.params)

    class Meta:
        ordering = ['-created_at']


class OrderExportLog(models.Model):
    SAMPLE = 'sample'
    COMPLETE = 'complete'
    TYPE_CHOICES = (
        (SAMPLE, 'Sample file'),
        (COMPLETE, 'Complete file')
    )

    started_by = models.DateTimeField(auto_now_add=True)
    finished_by = models.DateTimeField(blank=True, null=True)

    order_export = models.ForeignKey(OrderExport, related_name="logs", on_delete=models.CASCADE)
    successful = models.BooleanField(default=False)
    csv_url = models.CharField(max_length=512, blank=True, default='')
    type = models.CharField(max_length=100, choices=TYPE_CHOICES, default=SAMPLE)

    def __str__(self):
        return '<OrderExportLog {}>'.format(self.id)


@receiver(order_export_done)
def generate_reports(sender, order_export_pk, **kwargs):
    from leadgalaxy.tasks import generate_order_export, generate_order_export_query
    order_export = OrderExport.objects.get(pk=order_export_pk)
    order_export.url = ''
    order_export.sample_url = ''
    order_export.progress = 0
    order_export.save()

    if order_export.previous_day:
        api = ShopifyOrderExport(order_export)

        # Generate Sample Export
        api.generate_sample_export()
        generate_order_export_query.delay(order_export_pk)
    else:
        generate_order_export.delay(order_export_pk)
