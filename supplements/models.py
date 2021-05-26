import base64
from io import BytesIO
from decimal import Decimal

import arrow
import simplejson as json
from django.contrib.auth.models import User
from django.db import models
from django.utils.functional import cached_property
from PIL import Image

from lib.exceptions import capture_exception
from product_common import models as model_base
from shopified_core.utils import safe_float, get_store_api
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

SUPPLEMENTS_SUPPLIER = [
    'Supplements on Demand',
    'Dropified',
    'TLG',
    'PLS',
    'HurryHub',
]


class PLSupplement(PLSupplementMixin, model_base.Product):
    PRODUCT_TYPE = 'pls'

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
    is_active = models.BooleanField(default=True)
    inventory = models.PositiveIntegerField(default=9999)
    hs_code = models.CharField(max_length=255,
                               null=True,
                               default='2936.29.50.50',
                               verbose_name='HS (Harmonized System) code')

    def __str__(self):
        return self.title


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

    LABEL_STATUSES = [
        (DRAFT, 'Draft'),
        (APPROVED, 'Approved'),
        (AWAITING_REVIEW, 'In Review'),
        (REJECTED, 'Rejected'),
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
        self.image_url = upload_file_to_s3(url, self.user_supplement.user.id, prefix='/labels')
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
    sale_price = models.IntegerField()
    wholesale_price = models.IntegerField()
    shipping_price = models.IntegerField(default=0)
    taxes = models.IntegerField(default=0)
    duties = models.IntegerField(default=0)
    batch_number = models.CharField(max_length=30, null=True, blank=True)
    shipping_address_hash = models.CharField(max_length=250, null=True, blank=True)

    refund = models.OneToOneField('RefundPayments',
                                  related_name='refund_items',
                                  on_delete=models.SET_NULL,
                                  null=True,
                                  blank=True)

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

    def tracking_numbers_str(self):
        tracking_str = ""
        for pls_item in self.order_items.all():
            tracking_str += f' {pls_item.tracking_number},'
        return tracking_str.rstrip(',')


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

    is_label_printed = models.BooleanField(default=False)
    sale_price = models.IntegerField()
    wholesale_price = models.IntegerField()
    shipping_service = models.CharField(max_length=255, blank=True, null=True)
    is_bundled = models.BooleanField(default=False)
    order_track_id = models.BigIntegerField(null=True, blank=True)

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

    def save_order_track(self):
        if not self.order_track_id:
            self.create_tracking()

        self.update_tracking()

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
            'status': self.pls_order.status,
            'order': self.order_track_id,
            'order_details': json.dumps(self.pls_order.payment_details),
            'tracking_number': self.tracking_number,
            'source_id': self.pls_order.get_dropified_source_id(),
            'source_type': 'supplements',
        }
        if self.is_bundled:
            api_data['bundle'] = True

        try:
            response = self.store_api.post_order_fulfill_update(self.store_api_request, self.pls_order.user, api_data)
            if response.status_code != 200:
                result = json.loads(response.content.decode("utf-8"))
                raise Exception(result)
        except:
            capture_exception()


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
