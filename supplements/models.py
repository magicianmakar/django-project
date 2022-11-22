import base64
import re
from io import BytesIO
from decimal import Decimal

import arrow
import requests
import simplejson as json
from django.contrib.auth.models import User
from django.db import models
from django.urls import reverse
from django.utils.functional import cached_property
from PIL import Image

from lib.exceptions import capture_exception, capture_message
from product_common import models as model_base
from shopified_core.utils import safe_float, get_store_api, hash_text

from .mixin import (
    AuthorizeNetCustomerMixin,
    LabelCommentMixin,
    PayoutMixin,
    PLSOrderLineMixin,
    PLSOrderMixin,
    PLSupplementMixin,
    UserSupplementLabelMixin,
    UserSupplementMixin
)
from django.conf import settings
from shopified_core.utils import last_executed

SUPPLEMENTS_SUPPLIER = [
    'Supplements on Demand',
    'Dropified',
    'TLG',
    'PLS',
    'HurryHub',
]


class PLSupplement(PLSupplementMixin, model_base.Product):
    PRODUCT_TYPE = 'pls'

    shipstation_account = models.ForeignKey("ShipStationAccount", null=True, on_delete=models.SET_NULL)
    wholesale_price = models.DecimalField(max_digits=10, decimal_places=2)
    label_template_url = models.URLField()
    approved_label_url = models.URLField(null=True, blank=True)
    mockup_type = models.ForeignKey('MockupType',
                                    on_delete=models.CASCADE,
                                    related_name='mockup_type',
                                    null=True)
    label_size = models.ForeignKey('LabelSize',
                                   on_delete=models.SET_NULL,
                                   related_name='label_size',
                                   null=True)
    shipping_countries = models.ManyToManyField('ShippingGroup')
    product_information = models.TextField()
    authenticity_certificate_url = models.URLField()
    weight = models.DecimalField(max_digits=10, decimal_places=4, default=0)
    msrp = models.CharField(max_length=100, null=True, blank=True, verbose_name='MSRP')
    order_number_on_label = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    is_discontinued = models.BooleanField(default=False)
    is_new = models.BooleanField(default=False)
    on_sale = models.BooleanField(default=False)
    barcode_label = models.BooleanField(default=True)
    inventory = models.PositiveIntegerField(default=9999)
    hs_code = models.CharField(max_length=255,
                               null=True,
                               default='2936.29.50.50',
                               verbose_name='HS (Harmonized System) code')

    inventory_synced = False

    def __str__(self):
        return self.title

    # Gets called when an attribute is accessed
    def __getattribute__(self, item):
        if item == 'inventory':

            # sync inventory, but not often than once per 1 min
            if not self.inventory_synced and settings.PLOD_INVENTORY_API_HOST and not last_executed(f'plod_invsync_{self.id}', 60):
                try:
                    self.sync_inventory()
                except:
                    capture_message("Inventory sync failed")

            return super(PLSupplement, self).__getattribute__(item)

        # Calling the super class to avoid recursion
        return super(PLSupplement, self).__getattribute__(item)

    def sync_inventory(self):
        # trying to fetch inventory from parent DB
        inventory_response = requests.get(
            settings.PLOD_INVENTORY_API_HOST + '/api/supplements-public/inventory?shipstation_sku=' + self.shipstation_sku,
            verify=False, auth=self.get_inventory_auth()).json()
        if inventory_response['inventory']:
            self.inventory = inventory_response['inventory']
            self.inventory_synced = True
            self.save()

    def deduct_inventory(self, value):

        if settings.PLOD_INVENTORY_API_HOST:
            # deduct inventory on parent DB
            try:
                inventory_response = requests.post(
                    settings.PLOD_INVENTORY_API_HOST + '/api/supplements-public/decrease_inventory',
                    {'shipstation_sku': self.shipstation_sku, 'inventory': value},
                    verify=False, auth=self.get_inventory_auth()).json()
                if inventory_response['status'] == 'ok':
                    return inventory_response
                else:
                    return False
            except:
                capture_message("Inventory deduct failed")
        else:
            return True

    def get_inventory_auth(self):
        auth_username = list(settings.BASICAUTH_USERS.keys())[0]
        auth_password = settings.BASICAUTH_USERS[auth_username]
        return (auth_username, auth_password)


class ShippingGroup(models.Model):
    slug = models.CharField(max_length=100, unique=True)
    name = models.CharField(max_length=100)
    locations = models.TextField()
    immutable = models.BooleanField(default=False)
    data = models.TextField(null=True, blank=True, help_text='''Shipping rates (by weight) in the following Json format <pre>
        {
        "shipping_cost_default":{DEFAULT_COST},
        "shipping_rates":
                        [
                            {
                               "weight_from":{FROM_LB},
                               "weight_to":{TO_LB},
                               "shipping_cost":{COST}
                            },
                            {
                               "weight_from":{FROM_LB},
                               "weight_to":{TO_LB},
                               "shipping_cost":{COST}
                            }
                        ]
        }
        </pre>''')

    def __str__(self):
        if self.locations in self.name:
            return self.name
        else:
            return f'{self.name} ({self.locations})'

    def get_data(self):
        return json.loads(self.data)

    def set_data(self, cus):
        self.data = json.dumps(cus)
        self.save()

    def to_dict(self):
        return dict(
            slug=self.slug,
            name=self.name,
            locations=self.locations,
            immutable=self.immutable,
        )


class UserSupplement(UserSupplementMixin, models.Model):
    class Meta:
        ordering = ['-pk']
    title = models.CharField(max_length=200)
    description = models.TextField()
    category = models.CharField(max_length=200)
    tags = models.TextField()

    user = models.ForeignKey(User,
                             on_delete=models.CASCADE,
                             related_name='pl_supplements')

    pl_supplement = models.ForeignKey(PLSupplement,
                                      on_delete=models.CASCADE,
                                      related_name='user_pl_supplements')

    price = models.DecimalField(max_digits=10, decimal_places=2)
    compare_at_price = models.DecimalField(max_digits=10,
                                           decimal_places=2,
                                           blank=True,
                                           null=True)
    label_presets = models.TextField(default='{}', blank=True)
    current_label = models.OneToOneField('UserSupplementLabel',
                                         on_delete=models.SET_NULL,
                                         related_name='current_label_of',
                                         null=True)
    sample_product = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    is_deleted = models.BooleanField(default=False, blank=True)
    seen_users = models.TextField(default='', blank=True, null=True)

    def __str__(self):
        return self.title

    def get_weight(self, quantity):
        return self.pl_supplement.weight * quantity

    def get_label_presets_json(self):
        if self.label_presets != '{}':  # Custom presets from user
            return self.label_presets
        else:
            return json.dumps(self.pl_supplement.mockup_type.get_label_presets())


class UserSupplementImage(model_base.AbstractImage):
    user_supplement = models.ForeignKey(UserSupplement,
                                        on_delete=models.CASCADE,
                                        related_name='images')


class UserSupplementLabel(models.Model, UserSupplementLabelMixin):
    class Meta:
        ordering = ('-created_at',)

    DRAFT = 'draft'
    APPROVED = 'approved'
    AWAITING_REVIEW = 'awaiting'
    REJECTED = 'rejected'
    QA_PASSED = 'qapassed'

    LABEL_STATUSES = [
        (DRAFT, 'Draft'),
        (APPROVED, 'Approved'),
        (AWAITING_REVIEW, 'In Review'),
        (REJECTED, 'Rejected'),
        (QA_PASSED, 'QA Passed'),
    ]

    user_supplement = models.ForeignKey(UserSupplement,
                                        on_delete=models.CASCADE,
                                        related_name='labels')
    status = models.CharField(
        max_length=8,
        choices=LABEL_STATUSES,
        default=DRAFT,
    )

    url = models.URLField()
    sku = models.CharField(max_length=20, blank=True)
    image_url = models.URLField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def image(self):
        if self.image_url:
            return self.image_url

        from leadgalaxy.utils import upload_file_to_s3
        url = f'https://app.dropified.com/pdf/convert/?url={self.url}&ext=.png'
        self.image_url = upload_file_to_s3(
            url=re.sub(r'\.pdf$', '.png', self.url.split('/')[-1]),
            user_id=self.user_supplement.user.id,
            fp=BytesIO(requests.get(url).content),
            prefix='/labels'
        )
        self.save()

        return self.image_url

    @cached_property
    def status_updated_at(self):
        if self.status in [self.DRAFT, self.AWAITING_REVIEW]:
            return self.updated_at

        comment = self.comments.filter(new_status=self.status).order_by('-created_at').first()
        return comment.created_at if comment else self.updated_at

    def need_barcode_fix(self):
        # Between dates of below commits:
        # https://github.com/TheDevelopmentMachine/dropified-webapp/commit/e0d2d09d8aaf2cd3070ec21d210c49d5660f568e
        # https://github.com/TheDevelopmentMachine/dropified-webapp/commit/39ee21606c694a0fe29c208dab6bba0c903c0b08
        return arrow.get('2021-02-04') < arrow.get(self.updated_at) < arrow.get('2021-03-09')


class LabelComment(models.Model, LabelCommentMixin):
    label = models.ForeignKey(UserSupplementLabel,
                              on_delete=models.CASCADE,
                              related_name='comments')

    user = models.ForeignKey(User,
                             on_delete=models.CASCADE,
                             related_name='label_comments')

    text = models.TextField()
    new_status = models.CharField(max_length=8, blank=True, default='')
    is_private = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)


class PLSOrder(PLSOrderMixin, model_base.AbstractOrder):
    class Meta:
        ordering = 'shipstation_retries',

    sale_price = models.IntegerField()
    wholesale_price = models.IntegerField()
    shipping_price = models.IntegerField(default=0)
    taxes = models.IntegerField(default=0)
    duties = models.IntegerField(default=0)
    batch_number = models.CharField(max_length=30, null=True, blank=True)
    shipping_address_hash = models.CharField(max_length=250, null=True, blank=True)
    shipping_address = models.TextField(default='{}', null=True, blank=True)
    billing_address = models.TextField(default='{}', null=True, blank=True)
    shipstation_retries = models.PositiveIntegerField(default=0)

    refund = models.OneToOneField('RefundPayments',
                                  related_name='refund_items',
                                  on_delete=models.SET_NULL,
                                  null=True,
                                  blank=True)
    authorize_net_customer_id = models.CharField(
        max_length=255,
        null=True,
    )
    authorize_net_payment_id = models.CharField(
        max_length=255,
        null=True,
    )

    @property
    def payment_details(self):
        total_price = Decimal(self.amount) / Decimal(100)
        shipping_price = Decimal(self.shipping_price) / Decimal(100)
        products_price = total_price - shipping_price
        return {'cost': {
            'products': str(products_price.quantize(Decimal('0.01'))),
            'shipping': str(shipping_price.quantize(Decimal('0.01'))),
            'total': str(total_price.quantize(Decimal('0.01'))),
            'currency': 'USD',
        }}

    @property
    def source_url(self):
        return f"{reverse('pls:my_orders')}?transaction_id={self.id}"

    @property
    def source_status(self):
        return {
            PLSOrder.PENDING: 'D_PENDING_PAYMENT',
            PLSOrder.PAID: 'D_PAID',
            PLSOrder.SHIPPED: 'D_SHIPPED',
        }.get(self.status, 'PLACE_ORDER_SUCCESS')

    @cached_property
    def tracking_numbers_str(self):
        return ', '.join(self.order_items.exclude(tracking_number='').values_list('tracking_number', flat=True))

    @cached_property
    def shipping_service_id(self):
        first_item = self.order_items.first()
        return first_item.shipping_service_id if first_item else ''

    @cached_property
    def has_bundles(self):
        return self.order_items.filter(is_bundled=True).exists()

    @cached_property
    def shipstation_address(self):
        from supplements.lib.shipstation import get_address, prepare_shipping_data
        from shopified_core.models_utils import get_store_model

        if not self.shipping_address:
            store = get_store_model(self.store_type).objects.get(id=self.store_id)
            order = store.get_order(self.store_order_id)

            ship_to, bill_to = prepare_shipping_data(order)
            self.shipping_address_hash = hash_text(ship_to)
            self.shipping_address = ship_to
            self.billing_address = bill_to
            self.save()

            return self.shipstation_address
        else:
            return {
                'shipTo': get_address(json.loads(self.shipping_address)),
                'billTo': get_address(json.loads(self.billing_address)),
            }

    def to_shipstation_order(self, shipstation_acc):
        status = {
            'pending': 'awaiting_payment',
            'paid': 'awaiting_shipment',
            'shipped': 'shipped'
        }.get(self.status, 'awaiting_shipment')

        extra_info = {
            'items': [],
            'advancedOptions': {
                'customField1': self.order_number,
                'storeId': shipstation_acc.store_id
            }
        }

        if self.is_taxes_paid:
            extra_info['advancedOptions']['customField2'] = 'Duties Paid'

        if self.user.profile.company:
            extra_info['advancedOptions']['customField3'] = self.user.profile.company.vat

        if self.shipping_service_id:
            extra_info['requestedShippingService'] = self.shipping_service_id

        for item in self.order_items.all():
            item_pl_shipstation_acc = item.label.user_supplement.pl_supplement.shipstation_account
            if item_pl_shipstation_acc == shipstation_acc:
                extra_info['items'] += item.to_shipstation_item()

        return {
            **self.shipstation_address,
            **extra_info,
            'orderKey': str(self.id),
            'orderNumber': self.shipstation_order_number,
            'orderDate': self.created_at.isoformat(),
            'orderStatus': status,
            'amountPaid': self.amount / 100.,
        }


class PLSOrderLine(PLSOrderLineMixin, model_base.AbstractOrderLine):
    """
    Adding store_type, store_id, and order_id here so that we can run exists
    query atomically.
    """
    class Meta:
        unique_together = ['store_type',
                           'store_id',
                           'store_order_id',
                           'line_id',
                           'label']

    title = models.CharField(max_length=255, blank=True, default='')
    is_label_printed = models.BooleanField(default=False)
    sale_price = models.IntegerField()
    wholesale_price = models.IntegerField()
    shipping_service = models.CharField(max_length=255, blank=True, null=True)
    shipping_service_id = models.CharField(max_length=255, blank=True, default='')
    is_bundled = models.BooleanField(default=False)
    order_track_id = models.BigIntegerField(null=True, blank=True)
    batch_number = models.CharField(max_length=30, null=True, blank=True)

    label = models.ForeignKey(UserSupplementLabel,
                              on_delete=models.SET_NULL,
                              null=True,
                              related_name='orders')

    pls_order = models.ForeignKey(PLSOrder,
                                  on_delete=models.CASCADE,
                                  related_name='order_items',
                                  null=True)
    line_payout = models.ForeignKey('Payout',
                                    related_name='payout_lines',
                                    on_delete=models.SET_NULL,
                                    null=True,
                                    blank=True)
    shipping_payout = models.ForeignKey('Payout',
                                        related_name='ship_payout_lines',
                                        on_delete=models.SET_NULL,
                                        null=True,
                                        blank=True)
    refund_amount = models.DecimalField(max_digits=10,
                                        decimal_places=2,
                                        blank=True,
                                        null=True)
    cancelled_in_shipstation = models.BooleanField(default=False)

    @property
    def store_api(self):
        if not hasattr(self, '_store_api') or not self._store_api:
            self._store_api = get_store_api(self.store_type)
        return self._store_api

    @property
    def store_api_request(self):
        if not hasattr(self, '_store_api_request') or not self._store_api_request:
            class MockRequest:
                META = {}

            self._store_api_request = MockRequest()
        return self._store_api_request

    @property
    def source_url(self):
        return f"{reverse('pls:my_orders')}?item_id={self.id}"

    @cached_property
    def track(self):
        from shopified_core.models_utils import get_track_model
        try:
            return get_track_model(self.store_type).objects.get(id=self.order_track_id)
        except models.ObjectDoesNotExist:
            return None

    def save_order_track(self):
        if not self.order_track_id:
            self.create_tracking()

        self.update_tracking()
        self.save()

    def create_tracking(self):
        api_data = {
            'store': self.store_id,
            'order_id': self.store_order_id,
            'line_id': self.line_id,
            'aliexpress_order_id': self.pls_order.get_dropified_source_id(),
            'source_type': 'supplements',
        }

        try:
            response = self.store_api.post_order_fulfill(self.store_api_request, self.pls_order.user, api_data)
            result = json.loads(response.content.decode("utf-8"))
            if response.status_code == 200 and result.get('order_track_id'):
                self.order_track_id = result['order_track_id']
            else:
                raise Exception(result)
        except:
            capture_exception()

    def update_tracking(self):
        api_data = {
            'store': self.store_id,
            'status': self.pls_order.source_status,
            'order': self.order_track_id,
            'order_details': json.dumps(self.pls_order.payment_details),
            'tracking_number': self.tracking_number,
            'source_id': self.pls_order.get_dropified_source_id(),
            'source_type': 'supplements',
        }
        if self.is_bundled:
            api_data['bundle'] = True

        if self.tracking_number:
            self.is_fulfilled = True

        try:
            response = self.store_api.post_order_fulfill_update(self.store_api_request, self.pls_order.user, api_data)
            result = json.loads(response.content.decode("utf-8"))
            if response.status_code != 200:
                raise Exception(result)
        except:
            capture_exception()

    def to_shipstation_item(self):
        title = self.title or self.label.user_supplement.title
        if '**low stock**' in title.lower():
            title = re.sub(r'(\*\*.*?\*\*) ?', '', title)
        if self.label.user_supplement.pl_supplement.shipstation_account.labels_only:
            return [{'name': title,
                     'quantity': self.quantity,
                     'sku': self.label.sku,
                     'unitPrice': float(self.label.user_supplement.cost_price),
                     'imageUrl': self.label.image,
                     'lineItemKey': self.shipstation_key,
                     }]

        return [{
            'name': title,
            'quantity': self.quantity,
            'sku': self.label.user_supplement.shipstation_sku,
            'unitPrice': float(self.label.user_supplement.price),
            'imageUrl': self.label.image,
        }, {
            'name': f'Label for {title}',
            'quantity': self.quantity,
            'sku': self.label.sku,
            'unitPrice': 0,
            'imageUrl': self.label.image,
            'lineItemKey': self.shipstation_key,
        }]


class PLSUnpaidOrderManager(models.Manager):
    def get_queryset(self):
        prefetch_unpaid_orders = models.Prefetch(
            'plsorder_product_payments',
            to_attr='unpaid_orders',
            queryset=PLSOrder.objects.filter(models.Q(stripe_transaction_id='')
                                             | models.Q(stripe_transaction_id=None)),
        )
        return super().get_queryset() \
                      .prefetch_related(prefetch_unpaid_orders) \
                      .filter(models.Q(plsorder_product_payments__stripe_transaction_id='')
                              | models.Q(plsorder_product_payments__stripe_transaction_id=None),
                              plsorder_product_payments__isnull=False) \
                      .annotate(total=models.Sum('plsorder_product_payments__amount')) \
                      .order_by('email')


class UserUnpaidOrder(User):
    objects = PLSUnpaidOrderManager()

    class Meta:
        proxy = True

    def total_amount(self):
        return f'${(self.total / 100.):.2f}'


class Payout(PayoutMixin, model_base.AbstractPayout):
    shipping_cost = models.IntegerField(null=True, blank=True)
    supplier = models.ForeignKey(model_base.ProductSupplier,
                                 on_delete=models.SET_NULL,
                                 null=True,
                                 related_name='supplier_payouts')
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)


class AuthorizeNetCustomer(models.Model, AuthorizeNetCustomerMixin):
    class Meta:
        verbose_name = "Authorize.net Customer"
        verbose_name_plural = "Authorize.net Customers"

    user = models.OneToOneField(
        User,
        related_name='authorize_net_customer',
        on_delete=models.CASCADE,
    )

    customer_id = models.CharField(
        max_length=255,
        null=True,
        verbose_name='Profile ID',
    )

    payment_id = models.CharField(
        max_length=255,
        null=True,
        verbose_name='Payment Profile ID',
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Authorize.net Customer: {self.user.username}"


class LabelSize(models.Model):
    size = models.CharField(max_length=50, null=True, blank=True)

    def __str__(self):
        return self.size


class MockupType(models.Model):
    class Meta:
        ordering = 'name',

    slug = models.SlugField(max_length=100)
    name = models.CharField(max_length=255)
    presets = models.TextField(default='[]', blank=True)
    layers = models.TextField(default='[]', blank=True)

    def __str__(self):
        return self.name

    def get_label_presets(self):
        default_presets = [
            [{'left': -0.3}], [{'left': -0.3, 'layers': {'shadow': False}}],
            [{}], [{'layers': {'shadow': False}}],
            [{}, {}, {}], [{}, {}, {}, {}, {}],
        ]
        try:
            presets = json.loads(self.presets)
        except:
            presets = default_presets

        if not presets:
            presets = default_presets

        return presets

    def get_layers(self):
        try:
            layers = json.loads(self.layers)
        except:
            layers = []

        for layer in layers:
            if not layer.get('file'):
                continue

            mockup_folder = self.slug
            if 'colored-container-' in self.slug:
                mockup_folder = 'colored-container'

            image = Image.open(f"app/static/pls-mockup/{mockup_folder}/{layer['file']}")
            raw_image = BytesIO()
            ext = layer['file'].split('.')[-1]  # From PIL.Image.SAVE
            ext = {'jpg': 'jpeg'}.get(ext, ext)
            image.save(raw_image, format=ext)
            raw_image.seek(0)
            raw_image.name = layer['file']

            image_data = base64.b64encode(raw_image.getvalue()).decode()
            layer['file'] = f'data:image/{ext};base64,{image_data}'

        return layers


class RefundPayments(models.Model):

    REFUND_CHOICES = (
        ('refunded', 'Refunded'),
        ('voided', 'Voided'),
    )

    amount = models.DecimalField(max_digits=10, decimal_places=2)
    shipping = models.DecimalField(max_digits=10, decimal_places=2)
    description = models.TextField()
    fee = models.DecimalField(max_digits=10, decimal_places=2)
    transaction_id = models.CharField(max_length=255, null=True)
    status = models.CharField(choices=REFUND_CHOICES, default='refunded', max_length=8)
    order_shipped = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class BasketItem(models.Model):
    class Meta:
        ordering = ['-pk']

    quantity = models.IntegerField()
    user = models.ForeignKey(User,
                             on_delete=models.CASCADE,
                             related_name='basket_items')

    user_supplement = models.ForeignKey(UserSupplement,
                                        on_delete=models.CASCADE,
                                        related_name='basket_items')

    created_at = models.DateTimeField(auto_now_add=True)

    def total_price(self):

        return '%.02f' % (safe_float(self.user_supplement.pl_supplement.cost_price) * safe_float(self.quantity))


class BasketOrder(models.Model):
    class Meta:
        ordering = ['-pk']

    user = models.ForeignKey(User,
                             on_delete=models.CASCADE,
                             related_name='basket_orders')
    status = models.CharField(max_length=8, blank=True, default='')
    order_data = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def get_order(self):
        order_data = self.get_order_data()
        order_data['order_number'] = self.id
        return order_data

    def get_order_data(self):
        return json.loads(self.order_data)

    def set_order_data(self, data):
        self.order_data = json.dumps(data)
        self.save()

    def set_paid(self, paid_flag):
        if paid_flag:
            self.status = 'paid'
        else:
            self.status = ''


class ShipStationAccount(models.Model):
    class Meta:
        ordering = ['-pk']

    name = models.CharField(max_length=500)
    api_key = models.CharField(max_length=500)
    api_secret = models.CharField(max_length=500)
    api_url = models.URLField(default="https://ssapi.shipstation.com")
    max_retries = models.IntegerField(default=5)
    send_timeout = models.IntegerField(default=60)
    store_id = models.CharField(max_length=100, null=True, blank=True)
    labels_only = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name


class PLSReview(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    pl_supplement = models.ForeignKey(PLSupplement,
                                      on_delete=models.SET_NULL,
                                      null=True,
                                      related_name='pl_review')
    pls_order_line = models.ForeignKey(PLSOrderLine,
                                       on_delete=models.SET_NULL,
                                       null=True)
    product_quality_rating = models.PositiveSmallIntegerField()
    label_quality_rating = models.PositiveSmallIntegerField()
    delivery_rating = models.PositiveSmallIntegerField()
    comment = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'<PLSReview: {self.id}>'
