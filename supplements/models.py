import base64
from io import BytesIO

from django.contrib.auth.models import User
from django.db import models

import simplejson as json
from PIL import Image
from product_common import models as model_base
from shopified_core.utils import safe_float
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
SUPPLEMENTS_SUPPLIER = 'Supplements on Demand'


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
        if self.label_presets != '{}':
            return self.label_presets
        else:
            return json.dumps(self.pl_supplement.mockup_type.get_label_presets())


class UserSupplementImage(model_base.AbstractImage):
    user_supplement = models.ForeignKey(UserSupplement,
                                        on_delete=models.CASCADE,
                                        related_name='images')


class UserSupplementLabel(models.Model, UserSupplementLabelMixin):
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
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


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
    batch_number = models.CharField(max_length=30, null=True, blank=True)

    payout = models.ForeignKey('Payout',
                               related_name='payout_items',
                               on_delete=models.SET_NULL,
                               null=True,
                               blank=True)
    shipping_address_hash = models.CharField(max_length=250, null=True, blank=True)

    refund = models.OneToOneField('RefundPayments',
                                  related_name='refund_items',
                                  on_delete=models.SET_NULL,
                                  null=True,
                                  blank=True)


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

    label = models.ForeignKey(UserSupplementLabel,
                              on_delete=models.SET_NULL,
                              null=True,
                              related_name='orders')

    pls_order = models.ForeignKey(PLSOrder,
                                  on_delete=models.CASCADE,
                                  related_name='order_items',
                                  null=True)
    is_refunded = models.BooleanField(default=False)


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
        return f'${((self.total) / 100.):.2f}'


class Payout(PayoutMixin, model_base.AbstractPayout):
    shipping_cost = models.IntegerField(null=True, blank=True)


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
        verbose_name='Authorize.net Customer ID',
    )

    payment_id = models.CharField(
        max_length=255,
        null=True,
        verbose_name='Authorize.net Customer Payment ID',
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Authorize.net Customer: {self.user.username}"


class LabelSize(models.Model):
    slug = models.SlugField(max_length=100)
    height = models.DecimalField(max_digits=10, decimal_places=3)
    width = models.DecimalField(max_digits=10, decimal_places=3)

    def __str__(self):
        return f'{self.width}x{self.height}'


class MockupType(models.Model):
    slug = models.SlugField(max_length=100)
    name = models.CharField(max_length=255)

    def __str__(self):
        return self.name

    def get_label_presets(self):
        if self.slug == 'bottle':
            presets = [
                # front_shadow_mockup
                [{'left': 0.17, 'top': -0.57, 'size': 0.64}],
                # front_mockup
                [{'left': 0.17, 'top': -0.57, 'size': 0.64, 'layers': {'shadow': False}}],
                # back_shadow_mockup
                [{'left': -0.13, 'top': -0.57, 'size': 0.64}],
                # back_mockup
                [{'left': -0.13, 'top': -0.57, 'size': 0.64, 'layers': {'shadow': False}}],
                # group_of_3
                [
                    {'left': 0.17, 'top': -0.57, 'size': 0.64, 'bgLeft': -0.222, 'bgTop': 0.15, 'bgSize': 0.8},
                    {'left': 0.17, 'top': -0.57, 'size': 0.64, 'bgLeft': 0.425, 'bgTop': 0.15, 'bgSize': 0.8},
                    {'left': 0.17, 'top': -0.57, 'size': 0.64, 'bgLeft': 0.06, 'bgTop': 0.11, 'bgSize': 0.88}
                ],
                # group_of_5
                [
                    {'left': 0.17, 'top': -0.57, 'size': 0.64, 'bgLeft': -0.14, 'bgTop': 0.35, 'bgSize': 0.51},
                    {'left': 0.17, 'top': -0.57, 'size': 0.64, 'bgLeft': 0.62, 'bgTop': 0.35, 'bgSize': 0.51},
                    {'left': 0.17, 'top': -0.57, 'size': 0.64, 'bgLeft': -0.02, 'bgTop': 0.29, 'bgSize': 0.61},
                    {'left': 0.17, 'top': -0.57, 'size': 0.64, 'bgLeft': 0.4, 'bgTop': 0.29, 'bgSize': 0.61},
                    {'left': 0.17, 'top': -0.57, 'size': 0.64, 'bgLeft': 0.15, 'bgTop': 0.24, 'bgSize': 0.7}
                ],
            ]
        elif self.slug == 'container':
            presets = [
                [{'left': 0.44, 'top': 0.01, 'size': 0.41}],
                [{'left': 0.44, 'top': 0.01, 'size': 0.41, 'layers': {'shadow': False}}],
                [{'left': 0.05, 'top': -0.19, 'size': 0.57}],
                [{'left': 0.05, 'top': -0.19, 'size': 0.57, 'layers': {'shadow': False}}],
                [
                    {'name': 'Left', 'left': 0.44, 'top': 0.01, 'size': 0.41, 'bgLeft': -0.137, 'bgTop': 0.185, 'bgSize': 0.78},
                    {'name': 'Right', 'left': 0.44, 'top': 0.01, 'size': 0.4039, 'bgLeft': 0.3525, 'bgTop': 0.185, 'bgSize': 0.78},
                    {'name': 'Top', 'left': 0.44, 'top': 0.01, 'size': 0.41, 'bgLeft': 0.03, 'bgTop': 0.125, 'bgSize': 0.9005}
                ],
                [
                    {'name': '3 Left', 'left': 0.44, 'top': 0.01, 'size': 0.41, 'bgLeft': -0.0825, 'bgTop': 0.4, 'bgSize': 0.5},
                    {'name': '3 Right', 'left': 0.44, 'top': 0.01, 'size': 0.41, 'bgLeft': 0.585, 'bgTop': 0.4, 'bgSize': 0.5},
                    {'name': '2 Left', 'left': 0.44, 'top': 0.01, 'size': 0.41, 'bgLeft': 0.01, 'bgTop': 0.36, 'bgSize': 0.5738},
                    {'name': '2 Right', 'left': 0.44, 'top': 0.01, 'size': 0.41, 'bgLeft': 0.38, 'bgTop': 0.36, 'bgSize': 0.5738},
                    {'name': 'Top', 'left': 0.44, 'top': 0.01, 'size': 0.41, 'bgLeft': 0.1545, 'bgTop': 0.3225, 'bgSize': 0.6542}
                ]
            ]
        elif self.slug == 'tincture':
            presets = [
                [{'left': 0.06, 'top': -1.16, 'size': 0.92}],
                [{'left': 0.06, 'top': -1.16, 'size': 0.92, 'layers': {'shadow': False}}],
                [{'left': -0.22, 'top': -1.16, 'size': 0.92}],
                [{'left': -0.22, 'top': -1.16, 'size': 0.92, 'layers': {'shadow': False}}],
                [
                    {'left': 0.06, 'top': -1.16, 'size': 0.92, 'bgLeft': -0.26, 'bgTop': 0.02, 'bgSize': 1},
                    {'left': 0.06, 'top': -1.16, 'size': 0.92, 'bgLeft': 0.255, 'bgTop': 0.02, 'bgSize': 1},
                    {'left': 0.06, 'top': -1.16, 'size': 0.92, 'bgLeft': -0.04, 'bgTop': -0.03, 'bgSize': 1.08}
                ],
                [
                    {'left': 0.06, 'top': -1.16, 'size': 0.92, 'bgLeft': -0.31, 'bgTop': 0.11, 'bgSize': 0.86},
                    {'left': 0.06, 'top': -1.16, 'size': 0.92, 'bgLeft': 0.45, 'bgTop': 0.11, 'bgSize': 0.86},
                    {'left': 0.06, 'top': -1.16, 'size': 0.92, 'bgLeft': -0.20, 'bgTop': 0.02, 'bgSize': 1},
                    {'left': 0.06, 'top': -1.16, 'size': 0.92, 'bgLeft': 0.20, 'bgTop': 0.02, 'bgSize': 1},
                    {'left': 0.06, 'top': -1.16, 'size': 0.92, 'bgLeft': -0.04, 'bgTop': -0.03, 'bgSize': 1.08}
                ],
            ]
        elif self.slug == '4oz-bottle':
            presets = [
                [{'left': -0.53, 'top': -0.69, 'size': 1.7}],
                [{'left': -0.53, 'top': -0.69, 'size': 1.7, 'layers': {'shadow': False}}],
                [{'left': -0.29, 'top': -0.88, 'size': 2.06}],
                [{'left': -0.29, 'top': -0.88, 'size': 2.06, 'layers': {'shadow': False}}],
                [
                    {'left': -0.5465, 'top': -0.6803, 'size': 1.7, 'bgLeft': -0.3545, 'bgTop': -0.02, 'bgSize': 1.01},
                    {'left': -0.5465, 'top': -0.6803, 'size': 1.7, 'bgLeft': 0.2875, 'bgTop': -0.02, 'bgSize': 1.01},
                    {'left': -0.5465, 'top': -0.6803, 'size': 1.7, 'bgLeft': -0.1875, 'bgTop': -0.07, 'bgSize': 1.09},
                    {'left': -0.5465, 'top': -0.6803, 'size': 1.7, 'bgLeft': 0.035, 'bgTop': -0.07, 'bgSize': 1.09},
                ],
                [
                    {'left': -0.5465, 'top': -0.6803, 'size': 1.7, 'bgLeft': -0.2545, 'bgTop': 0.2125, 'bgSize': 0.6238},
                    {'left': -0.5465, 'top': -0.6803, 'size': 1.7, 'bgLeft': 0.6125, 'bgTop': 0.23, 'bgSize': 0.6146},
                    {'left': -0.5465, 'top': -0.6803, 'size': 1.7, 'bgLeft': -0.175, 'bgTop': 0.1875, 'bgSize': 0.6767},
                    {'left': -0.5465, 'top': -0.6803, 'size': 1.7, 'bgLeft': 0.475, 'bgTop': 0.2025, 'bgSize': 0.6616},
                    {'left': -0.5465, 'top': -0.6803, 'size': 1.7, 'bgLeft': -0.0895, 'bgTop': 0.16, 'bgSize': 0.7313},
                    {'left': -0.5465, 'top': -0.6803, 'size': 1.7, 'bgLeft': 0.3175, 'bgTop': 0.1625, 'bgSize': 0.7308},
                    {'left': -0.5465, 'top': -0.6803, 'size': 1.7, 'bgLeft': 0.0025, 'bgTop': 0.1325, 'bgSize': 0.7892},
                    {'left': -0.5465, 'top': -0.6803, 'size': 1.7, 'bgLeft': 0.17, 'bgTop': 0.135, 'bgSize': 0.7892},
                ],
            ]
        elif 'colored-container-' in self.slug:
            presets = [
                [{'left': 0.22, 'top': -0.97, 'size': 0.60}],
                [{'left': 0.22, 'top': -0.97, 'size': 0.60, 'layers': {'shadow': False}}],
                [{'left': -0.15, 'top': -0.92, 'size': 0.6}],
                [{'left': -0.15, 'top': -0.92, 'size': 0.6, 'layers': {'shadow': False}}],
                [
                    {'name': 'Left', 'left': 0.22, 'top': -0.97, 'size': 0.60, 'bgLeft': -0.137, 'bgTop': 0.045, 'bgSize': 0.78},
                    {'name': 'Right', 'left': 0.22, 'top': -0.97, 'size': 0.60, 'bgLeft': 0.3525, 'bgTop': 0.045, 'bgSize': 0.78},
                    {'name': 'Top', 'left': 0.22, 'top': -0.97, 'size': 0.60, 'bgLeft': 0.03, 'bgTop': -0.015, 'bgSize': 0.9005}
                ],
                [
                    {'name': '3 Left', 'left': 0.22, 'top': -0.97, 'size': 0.60, 'bgLeft': -0.0825, 'bgTop': 0.23, 'bgSize': 0.5},
                    {'name': '3 Right', 'left': 0.22, 'top': -0.97, 'size': 0.60, 'bgLeft': 0.585, 'bgTop': 0.23, 'bgSize': 0.5},
                    {'name': '2 Left', 'left': 0.22, 'top': -0.97, 'size': 0.60, 'bgLeft': 0.01, 'bgTop': 0.19, 'bgSize': 0.5738},
                    {'name': '2 Right', 'left': 0.22, 'top': -0.97, 'size': 0.60, 'bgLeft': 0.38, 'bgTop': 0.19, 'bgSize': 0.5738},
                    {'name': 'Top', 'left': 0.22, 'top': -0.97, 'size': 0.60, 'bgLeft': 0.1545, 'bgTop': 0.15, 'bgSize': 0.6542}
                ]
            ]
        elif self.slug == '2500cc-powder-container':
            presets = [
                [{'left': 0.19, 'top': -0.83, 'size': 0.6}],
                [{'left': 0.19, 'top': -0.83, 'size': 0.6, 'layers': {'shadow': False}}],
                [{'left': 0.6, 'top': -0.83, 'size': 0.6}],
                [{'left': 0.6, 'top': -0.83, 'size': 0.6, 'layers': {'shadow': False}}],
                [
                    {'left': 0.19, 'top': -0.83, 'size': 0.6, 'bgLeft': -0.172, 'bgTop': 0.1, 'bgSize': 0.77},
                    {'left': 0.19, 'top': -0.83, 'size': 0.6, 'bgLeft': 0.4025, 'bgTop': 0.1, 'bgSize': 0.77},
                    {'left': 0.19, 'top': -0.83, 'size': 0.6, 'bgLeft': 0.0725, 'bgTop': 0.07, 'bgSize': 0.85}
                ],
                [
                    {'left': 0.19, 'top': -0.83, 'size': 0.6, 'bgLeft': -0.11, 'bgTop': 0.27, 'bgSize': 0.51},
                    {'left': 0.19, 'top': -0.83, 'size': 0.6, 'bgLeft': 0.59, 'bgTop': 0.27, 'bgSize': 0.51},
                    {'left': 0.19, 'top': -0.83, 'size': 0.6, 'bgLeft': -0.02, 'bgTop': 0.21, 'bgSize': 0.61},
                    {'left': 0.19, 'top': -0.83, 'size': 0.6, 'bgLeft': 0.4, 'bgTop': 0.21, 'bgSize': 0.61},
                    {'left': 0.19, 'top': -0.83, 'size': 0.6, 'bgLeft': 0.15, 'bgTop': 0.16, 'bgSize': 0.7}
                ],
            ]
        elif self.slug in ['sour-gummies-bottle', 'cdb-gummies']:
            presets = [
                [{'left': 0.2, 'top': -0.5, 'size': 0.68}],
                [{'left': 0.2, 'top': -0.5, 'size': 0.68, 'layers': {'shadow': False}}],
                [{'left': -0.13, 'top': -0.55, 'size': 0.71}],
                [{'left': -0.13, 'top': -0.55, 'size': 0.71, 'layers': {'shadow': False}}],
                [
                    {'left': 0.2, 'top': -0.5, 'size': 0.68, 'bgLeft': -0.222, 'bgTop': 0.15, 'bgSize': 0.8},
                    {'left': 0.2, 'top': -0.5, 'size': 0.68, 'bgLeft': 0.425, 'bgTop': 0.15, 'bgSize': 0.8},
                    {'left': 0.2, 'top': -0.5, 'size': 0.68, 'bgLeft': 0.06, 'bgTop': 0.11, 'bgSize': 0.88}
                ],
                [
                    {'left': 0.2, 'top': -0.5, 'size': 0.68, 'bgLeft': -0.14, 'bgTop': 0.35, 'bgSize': 0.51},
                    {'left': 0.2, 'top': -0.5, 'size': 0.68, 'bgLeft': 0.62, 'bgTop': 0.35, 'bgSize': 0.51},
                    {'left': 0.2, 'top': -0.5, 'size': 0.68, 'bgLeft': -0.02, 'bgTop': 0.29, 'bgSize': 0.61},
                    {'left': 0.2, 'top': -0.5, 'size': 0.68, 'bgLeft': 0.4, 'bgTop': 0.29, 'bgSize': 0.61},
                    {'left': 0.2, 'top': -0.5, 'size': 0.68, 'bgLeft': 0.15, 'bgTop': 0.24, 'bgSize': 0.7}
                ],
            ]
        elif self.slug == '2oz-pump-bottle':
            presets = [
                [{'left': 0.13, 'top': -0.83, 'size': 0.78}],
                [{'left': 0.13, 'top': -0.83, 'size': 0.78, 'layers': {'shadow': False}}],
                [{'left': 0.27, 'top': -1.36, 'size': 1.1}],
                [{'left': 0.27, 'top': -1.36, 'size': 1.1, 'layers': {'shadow': False}}],
                [
                    {'left': 0.13, 'top': -0.83, 'size': 0.78, 'bgLeft': -0.24, 'bgTop': 0.06, 'bgSize': 0.93},
                    {'left': 0.13, 'top': -0.83, 'size': 0.78, 'bgLeft': 0.26, 'bgTop': 0.06, 'bgSize': 0.93},
                    {'left': 0.13, 'top': -0.83, 'size': 0.78, 'bgLeft': -0.04, 'bgTop': 0.01, 'bgSize': 1.03}
                ],
                [
                    {'left': 0.13, 'top': -0.83, 'size': 0.78, 'bgLeft': -0.27, 'bgTop': 0.13, 'bgSize': 0.74},
                    {'left': 0.13, 'top': -0.83, 'size': 0.78, 'bgLeft': 0.52, 'bgTop': 0.13, 'bgSize': 0.74},
                    {'left': 0.13, 'top': -0.83, 'size': 0.78, 'bgLeft': -0.17, 'bgTop': 0.075, 'bgSize': 0.89},
                    {'left': 0.13, 'top': -0.83, 'size': 0.78, 'bgLeft': 0.27, 'bgTop': 0.075, 'bgSize': 0.89},
                    {'left': 0.13, 'top': -0.83, 'size': 0.78, 'bgLeft': -0.017, 'bgTop': 0.025, 'bgSize': 1.02}
                ]
            ]
        elif self.slug == '4oz-cosmetic-jar':
            presets = [
                [{'left': 0.27, 'top': -2.61, 'size': 0.51, 'bgTop': -0.17}],
                [{'left': 0.27, 'top': -2.61, 'size': 0.51, 'bgTop': -0.17, 'layers': {'shadow': False}}],
                [{'left': 0.27, 'top': -2.61, 'size': 0.51, 'bgTop': -0.17}],
                [{'left': 0.27, 'top': -2.61, 'size': 0.51, 'bgTop': -0.17, 'layers': {'shadow': False}}],
                [
                    {'name': 'Left', 'left': 0.27, 'top': -2.61, 'size': 0.51, 'bgLeft': -0.09, 'bgTop': 0.06, 'bgSize': 0.64},
                    {'name': 'Right', 'left': 0.27, 'top': -2.61, 'size': 0.51, 'bgLeft': 0.44, 'bgTop': 0.06, 'bgSize': 0.64},
                    {'name': 'Top', 'left': 0.27, 'top': -2.61, 'size': 0.51, 'bgLeft': 0.105, 'bgTop': -0.01, 'bgSize': 0.77}
                ],
                [
                    {'name': '3 Left', 'left': 0.27, 'top': -2.61, 'size': 0.51, 'bgLeft': -0.057, 'bgTop': 0.28, 'bgSize': 0.41},
                    {'name': '3 Right', 'left': 0.27, 'top': -2.61, 'size': 0.51, 'bgLeft': 0.64, 'bgTop': 0.28, 'bgSize': 0.41},
                    {'name': '2 Left', 'left': 0.27, 'top': -2.61, 'size': 0.51, 'bgLeft': 0.03, 'bgTop': 0.2, 'bgSize': 0.52},
                    {'name': '2 Right', 'left': 0.27, 'top': -2.61, 'size': 0.51, 'bgLeft': 0.42, 'bgTop': 0.2, 'bgSize': 0.52},
                    {'name': 'Top', 'left': 0.27, 'top': -2.61, 'size': 0.51, 'bgLeft': 0.18, 'bgTop': 0.13, 'bgSize': 0.63}
                ]
            ]
        elif self.slug == 'exfoliating-cleanser':
            presets = [
                [{'left': -0.53, 'top': -0.69, 'size': 1.7}],
                [{'left': -0.53, 'top': -0.69, 'size': 1.7, 'layers': {'shadow': False}}],
                [{'left': -0.29, 'top': -0.88, 'size': 2.06}],
                [{'left': -0.29, 'top': -0.88, 'size': 2.06, 'layers': {'shadow': False}}],
                [
                    {'left': -0.5465, 'top': -0.6803, 'size': 1.7, 'bgLeft': -0.3545, 'bgTop': -0.02, 'bgSize': 1.01},
                    {'left': -0.5465, 'top': -0.6803, 'size': 1.7, 'bgLeft': 0.2875, 'bgTop': -0.02, 'bgSize': 1.01},
                    {'left': -0.5465, 'top': -0.6803, 'size': 1.7, 'bgLeft': -0.1875, 'bgTop': -0.07, 'bgSize': 1.09},
                    {'left': -0.5465, 'top': -0.6803, 'size': 1.7, 'bgLeft': 0.035, 'bgTop': -0.07, 'bgSize': 1.09},
                ],
                [
                    {'left': -0.5465, 'top': -0.6803, 'size': 1.7, 'bgLeft': -0.2545, 'bgTop': 0.2125, 'bgSize': 0.6238},
                    {'left': -0.5465, 'top': -0.6803, 'size': 1.7, 'bgLeft': 0.6125, 'bgTop': 0.23, 'bgSize': 0.6146},
                    {'left': -0.5465, 'top': -0.6803, 'size': 1.7, 'bgLeft': -0.175, 'bgTop': 0.1875, 'bgSize': 0.6767},
                    {'left': -0.5465, 'top': -0.6803, 'size': 1.7, 'bgLeft': 0.475, 'bgTop': 0.2025, 'bgSize': 0.6616},
                    {'left': -0.5465, 'top': -0.6803, 'size': 1.7, 'bgLeft': -0.0895, 'bgTop': 0.16, 'bgSize': 0.7313},
                    {'left': -0.5465, 'top': -0.6803, 'size': 1.7, 'bgLeft': 0.3175, 'bgTop': 0.1625, 'bgSize': 0.7308},
                    {'left': -0.5465, 'top': -0.6803, 'size': 1.7, 'bgLeft': 0.0025, 'bgTop': 0.1325, 'bgSize': 0.7892},
                    {'left': -0.5465, 'top': -0.6803, 'size': 1.7, 'bgLeft': 0.17, 'bgTop': 0.135, 'bgSize': 0.7892},
                ],
            ]
        elif self.slug == '1oz-pump-bottle':
            presets = [
                [{'left': -0.16, 'top': -1.38, 'size': 1.36}],
                [{'left': -0.16, 'top': -1.38, 'size': 1.36, 'layers': {'shadow': False}}],
                [{'left': -0.16, 'top': -1.38, 'size': 1.36}],
                [{'left': -0.16, 'top': -1.38, 'size': 1.36, 'layers': {'shadow': False}}],
                [
                    {'left': -0.16, 'top': -1.38, 'size': 1.36, 'bgLeft': -0.252, 'bgTop': -0.06, 'bgSize': 1.08},
                    {'left': -0.16, 'top': -1.38, 'size': 1.36, 'bgLeft': 0.175, 'bgTop': -0.06, 'bgSize': 1.08},
                    {'left': -0.16, 'top': -1.38, 'size': 1.36, 'bgLeft': -0.09, 'bgTop': -0.1325, 'bgSize': 1.18}
                ],
                [
                    {'left': -0.16, 'top': -1.38, 'size': 1.36, 'bgLeft': -0.37, 'bgTop': 0.03, 'bgSize': 0.94},
                    {'left': -0.16, 'top': -1.38, 'size': 1.36, 'bgLeft': 0.42, 'bgTop': 0.03, 'bgSize': 0.94},
                    {'left': -0.16, 'top': -1.38, 'size': 1.36, 'bgLeft': -0.252, 'bgTop': -0.06, 'bgSize': 1.08},
                    {'left': -0.16, 'top': -1.38, 'size': 1.36, 'bgLeft': 0.175, 'bgTop': -0.06, 'bgSize': 1.08},
                    {'left': -0.16, 'top': -1.38, 'size': 1.36, 'bgLeft': -0.09, 'bgTop': -0.1325, 'bgSize': 1.18}
                ],
            ]
        elif self.slug == '4oz-pump-bottle':
            presets = [
                [{'left': -0.054, 'top': -1.153, 'size': 1.205}],
                [{'left': -0.054, 'top': -1.153, 'size': 1.205, 'layers': {'shadow': False}}],
                [{'left': 0.325, 'top': -1.012, 'size': 1.062}],
                [{'left': 0.325, 'top': -1.012, 'size': 1.062, 'layers': {'shadow': False}}],
                [
                    {'left': -0.054, 'top': -1.153, 'size': 1.205, 'bgLeft': -0.34, 'bgTop': -0.07, 'bgSize': 1.08},
                    {'left': -0.054, 'top': -1.167, 'size': 1.205, 'bgLeft': 0.213, 'bgTop': -0.078, 'bgSize': 1.08},
                    {'left': -0.054, 'top': -1.153, 'size': 1.205, 'bgLeft': -0.118, 'bgTop': -0.133, 'bgSize': 1.18}
                ],
                [
                    {'left': -0.054, 'top': -1.153, 'size': 1.205, 'bgLeft': -0.332, 'bgTop': -0.002, 'bgSize': 0.94},
                    {'left': -0.054, 'top': -1.153, 'size': 1.205, 'bgLeft': 0.372, 'bgTop': 0, 'bgSize': 0.94},
                    {'left': -0.054, 'top': -1.153, 'size': 1.205, 'bgLeft': -0.232, 'bgTop': -0.078, 'bgSize': 1.08},
                    {'left': -0.054, 'top': -1.153, 'size': 1.205, 'bgLeft': 0.137, 'bgTop': -0.073, 'bgSize': 1.08},
                    {'left': -0.054, 'top': -1.153, 'size': 1.205, 'bgLeft': -0.09, 'bgTop': -0.133, 'bgSize': 1.18}
                ],
            ]
        elif self.slug == '44oz-jar-black-lid':
            presets = [
                [{'left': 0.136, 'top': -1.461, 'size': 0.711, 'bgLeft': -0.223, 'bgTop': -0.395, 'bgSize': 1.429}],
                [{'left': 0.136, 'top': -1.461, 'size': 0.711, 'bgLeft': -0.223, 'bgTop': -0.395, 'bgSize': 1.429, 'layers': {'shadow': False}}],
                [{'left': 0.136, 'top': -1.461, 'size': 0.711, 'bgLeft': -0.223, 'bgTop': -0.395, 'bgSize': 1.429}],
                [{'left': 0.136, 'top': -1.461, 'size': 0.711, 'bgLeft': -0.223, 'bgTop': -0.395, 'bgSize': 1.429, 'layers': {'shadow': False}}],
                [
                    {'left': 0.136, 'top': -1.461, 'size': 0.711, 'bgLeft': -0.2, 'bgTop': 0.013, 'bgSize': 0.833},
                    {'left': 0.136, 'top': -1.461, 'size': 0.711, 'bgLeft': 0.353, 'bgTop': 0.013, 'bgSize': 0.833},
                    {'left': 0.136, 'top': -1.461, 'size': 0.711, 'bgLeft': 0.022, 'bgTop': -0.051, 'bgSize': 0.91}
                ],
                [
                    {'left': 0.136, 'top': -1.461, 'size': 0.711, 'bgLeft': -0.152, 'bgTop': 0.151, 'bgSize': 0.599},
                    {'left': 0.136, 'top': -1.461, 'size': 0.711, 'bgLeft': 0.539, 'bgTop': 0.151, 'bgSize': 0.599},
                    {'left': 0.136, 'top': -1.461, 'size': 0.711, 'bgLeft': -0.074, 'bgTop': 0.055, 'bgSize': 0.737},
                    {'left': 0.136, 'top': -1.461, 'size': 0.711, 'bgLeft': 0.305, 'bgTop': 0.055, 'bgSize': 0.737},
                    {'left': 0.136, 'top': -1.461, 'size': 0.711, 'bgLeft': 0.04, 'bgTop': -0.04, 'bgSize': 0.873}
                ],
            ]
        elif self.slug == '32oz-jar-black-lid':
            presets = [
                [{'left': 0.155, 'top': -0.449, 'size': 0.694}],
                [{'left': 0.155, 'top': -0.449, 'size': 0.694, 'layers': {'shadow': False}}],
                [{'left': 0.637, 'top': -0.254, 'size': 0.49}],
                [{'left': 0.637, 'top': -0.254, 'size': 0.49, 'layers': {'shadow': False}}],
                [
                    {'left': 0.151, 'top': -0.449, 'size': 0.685, 'bgLeft': -0.178, 'bgTop': 0.128, 'bgSize': 0.802},
                    {'left': 0.151, 'top': -0.449, 'size': 0.685, 'bgLeft': 0.358, 'bgTop': 0.131, 'bgSize': 0.802},
                    {'left': 0.151, 'top': -0.449, 'size': 0.685, 'bgLeft': 0.005, 'bgTop': 0.039, 'bgSize': 0.952}
                ],
                [
                    {'left': 0.155, 'top': -0.449, 'size': 0.694, 'bgLeft': -0.147, 'bgTop': 0.261, 'bgSize': 0.599},
                    {'left': 0.155, 'top': -0.449, 'size': 0.694, 'bgLeft': 0.544, 'bgTop': 0.261, 'bgSize': 0.599},
                    {'left': 0.155, 'top': -0.449, 'size': 0.694, 'bgLeft': -0.069, 'bgTop': 0.178, 'bgSize': 0.737},
                    {'left': 0.155, 'top': -0.449, 'size': 0.694, 'bgLeft': 0.31, 'bgTop': 0.178, 'bgSize': 0.737},
                    {'left': 0.155, 'top': -0.449, 'size': 0.694, 'bgLeft': 0.045, 'bgTop': 0.093, 'bgSize': 0.873}
                ],
            ]
        elif self.slug == '16oz-jar-black-lid':
            presets = [
                [{'left': 0.098, 'top': -1.759, 'size': 0.804, 'bgLeft': -0.26, 'bgTop': -0.463, 'bgSize': 1.457}],
                [{'left': 0.098, 'top': -1.759, 'size': 0.804, 'bgLeft': -0.26, 'bgTop': -0.463, 'bgSize': 1.457, 'layers': {'shadow': False}}],
                [{'left': 0.459, 'top': -1.773, 'size': 0.804, 'bgLeft': -0.26, 'bgTop': -0.463, 'bgSize': 1.457}],
                [{'left': 0.459, 'top': -1.773, 'size': 0.804, 'bgLeft': -0.26, 'bgTop': -0.463, 'bgSize': 1.457, 'layers': {'shadow': False}}],
                [
                    {'left': 0.098, 'top': -1.759, 'size': 0.804, 'bgLeft': -0.211, 'bgTop': -0.005, 'bgSize': 0.829},
                    {'left': 0.098, 'top': -1.759, 'size': 0.804, 'bgLeft': 0.358, 'bgTop': -0.005, 'bgSize': 0.829},
                    {'left': 0.098, 'top': -1.759, 'size': 0.804, 'bgLeft': -0.078, 'bgTop': -0.199, 'bgSize': 1.087}
                ],
                [
                    {'left': 0.098, 'top': -1.759, 'size': 0.804, 'bgLeft': -0.177, 'bgTop': 0.166, 'bgSize': 0.628},
                    {'left': 0.098, 'top': -1.759, 'size': 0.804, 'bgLeft': 0.539, 'bgTop': 0.166, 'bgSize': 0.628},
                    {'left': 0.098, 'top': -1.759, 'size': 0.804, 'bgLeft': -0.107, 'bgTop': 0.05, 'bgSize': 0.784},
                    {'left': 0.098, 'top': -1.759, 'size': 0.804, 'bgLeft': 0.3, 'bgTop': 0.05, 'bgSize': 0.784},
                    {'left': 0.098, 'top': -1.759, 'size': 0.804, 'bgLeft': -0.025, 'bgTop': -0.132, 'bgSize': 1.016}
                ],
            ]
        elif self.slug == '4oz-jar':
            presets = [
                [{'left': 0.344, 'top': -0.668, 'size': 0.393}],
                [{'left': 0.344, 'top': -0.668, 'size': 0.393, 'layers': {'shadow': False}}],
                [{'left': -0.021, 'top': -0.83, 'size': 0.436}],
                [{'left': -0.021, 'top': -0.83, 'size': 0.436, 'layers': {'shadow': False}}],
                [
                    {'left': 0.344, 'top': -0.668, 'size': 0.393, 'name': 'Left', 'bgLeft': -0.137, 'bgTop': 0.097, 'bgSize': 0.78},
                    {'left': 0.344, 'top': -0.668, 'size': 0.393, 'name': 'Right', 'bgLeft': 0.352, 'bgTop': 0.097, 'bgSize': 0.78},
                    {'left': 0.344, 'top': -0.668, 'size': 0.393, 'name': 'Top', 'bgLeft': 0.03, 'bgTop': 0.037, 'bgSize': 0.9}
                ],
                [
                    {'left': 0.344, 'top': -0.668, 'size': 0.386, 'name': '3 Left', 'bgLeft': -0.088, 'bgTop': 0.27, 'bgSize': 0.5},
                    {'left': 0.344, 'top': -0.668, 'size': 0.386, 'name': '3 Right', 'bgLeft': 0.58, 'bgTop': 0.27, 'bgSize': 0.5},
                    {'left': 0.344, 'top': -0.668, 'size': 0.386, 'name': '2 Left', 'bgLeft': 0.005, 'bgTop': 0.23, 'bgSize': 0.574},
                    {'left': 0.344, 'top': -0.668, 'size': 0.386, 'name': '2 Right', 'bgLeft': 0.375, 'bgTop': 0.23, 'bgSize': 0.574},
                    {'left': 0.344, 'top': -0.668, 'size': 0.386, 'name': 'Top', 'bgLeft': 0.149, 'bgTop': 0.192, 'bgSize': 0.654}
                ]
            ]
        elif self.slug == '8oz-bottle':
            presets = [
                [{'left': -0.361, 'top': -0.486, 'size': 1.398}],
                [{'left': -0.361, 'top': -0.486, 'size': 1.398, 'layers': {'shadow': False}}],
                [{'left': 0.014, 'top': -0.588, 'size': 1.534}],
                [{'left': 0.014, 'top': -0.588, 'size': 1.534, 'layers': {'shadow': False}}],
                [
                    {'left': -0.361, 'top': -0.486, 'size': 1.398, 'bgLeft': -0.247, 'bgTop': 0.098, 'bgSize': 0.866},
                    {'left': -0.361, 'top': -0.486, 'size': 1.398, 'bgLeft': 0.355, 'bgTop': 0.1, 'bgSize': 0.866},
                    {'left': -0.361, 'top': -0.486, 'size': 1.398, 'bgLeft': -0.082, 'bgTop': 0.05, 'bgSize': 0.934},
                    {'left': -0.361, 'top': -0.486, 'size': 1.398, 'bgLeft': 0.118, 'bgTop': 0.05, 'bgSize': 0.934}
                ],
                [
                    {'left': -0.361, 'top': -0.486, 'size': 1.398, 'bgLeft': -0.2545, 'bgTop': 0.2125, 'bgSize': 0.6238},
                    {'left': -0.361, 'top': -0.486, 'size': 1.398, 'bgLeft': 0.6125, 'bgTop': 0.23, 'bgSize': 0.6146},
                    {'left': -0.361, 'top': -0.486, 'size': 1.398, 'bgLeft': -0.175, 'bgTop': 0.1875, 'bgSize': 0.6767},
                    {'left': -0.361, 'top': -0.486, 'size': 1.398, 'bgLeft': 0.475, 'bgTop': 0.2025, 'bgSize': 0.6616},
                    {'left': -0.361, 'top': -0.486, 'size': 1.398, 'bgLeft': -0.0895, 'bgTop': 0.16, 'bgSize': 0.7313},
                    {'left': -0.361, 'top': -0.486, 'size': 1.398, 'bgLeft': 0.3175, 'bgTop': 0.1625, 'bgSize': 0.7308},
                    {'left': -0.361, 'top': -0.486, 'size': 1.398, 'bgLeft': 0.0025, 'bgTop': 0.1325, 'bgSize': 0.7892},
                    {'left': -0.361, 'top': -0.486, 'size': 1.398, 'bgLeft': 0.17, 'bgTop': 0.135, 'bgSize': 0.7892},
                ],
            ]
        elif self.slug == '20oz-black-jar':
            presets = [
                [{'left': 0.085, 'top': -1.768, 'size': 0.839}],
                [{'left': 0.085, 'top': -1.768, 'size': 0.839, 'layers': {'shadow': False}}],
                [{'left': 0.47, 'top': -1.787, 'size': 0.839}],
                [{'left': 0.47, 'top': -1.787, 'size': 0.839, 'layers': {'shadow': False}}],
                [
                    {'left': 0.085, 'top': -1.768, 'size': 0.839, 'bgLeft': -0.202, 'bgTop': 0.05, 'bgSize': 0.77},
                    {'left': 0.085, 'top': -1.768, 'size': 0.839, 'bgLeft': 0.415, 'bgTop': 0.042, 'bgSize': 0.773},
                    {'left': 0.085, 'top': -1.768, 'size': 0.839, 'bgLeft': 0.022, 'bgTop': -0.068, 'bgSize': 0.929}
                ],
                [
                    {'left': 0.085, 'top': -1.768, 'size': 0.839, 'bgLeft': -0.14, 'bgTop': 0.207, 'bgSize': 0.51},
                    {'left': 0.085, 'top': -1.768, 'size': 0.839, 'bgLeft': 0.62, 'bgTop': 0.207, 'bgSize': 0.51},
                    {'left': 0.085, 'top': -1.768, 'size': 0.839, 'bgLeft': -0.02, 'bgTop': 0.147, 'bgSize': 0.61},
                    {'left': 0.085, 'top': -1.768, 'size': 0.839, 'bgLeft': 0.4, 'bgTop': 0.147, 'bgSize': 0.61},
                    {'left': 0.085, 'top': -1.768, 'size': 0.839, 'bgLeft': 0.15, 'bgTop': 0.097, 'bgSize': 0.7}
                ],
            ]
        elif self.slug == 'coffee-bag':
            presets = [
                [{'left': -1.123, 'top': -1.003, 'size': 3.21}],
                [{'left': -1.123, 'top': -1.003, 'size': 3.21, 'layers': {'shadow': False}}],
                [{'left': -1.123, 'top': -1.003, 'size': 3.21}],
                [{'left': -1.123, 'top': -1.003, 'size': 3.21, 'layers': {'shadow': False}}],
                [
                    {'left': -1.123, 'top': -1.003, 'size': 3.21, 'bgLeft': -0.255, 'bgTop': 0.032, 'bgSize': 0.936},
                    {'left': -1.123, 'top': -1.003, 'size': 3.21, 'bgLeft': 0.272, 'bgTop': 0.032, 'bgSize': 0.936},
                    {'left': -1.123, 'top': -1.003, 'size': 3.21, 'bgLeft': -0.061, 'bgTop': -0.038, 'bgSize': 1.083}
                ],
                [
                    {'left': -1.123, 'top': -1.003, 'size': 3.21, 'bgLeft': -0.17, 'bgTop': 0.225, 'bgSize': 0.572},
                    {'left': -1.123, 'top': -1.003, 'size': 3.21, 'bgLeft': 0.578, 'bgTop': 0.225, 'bgSize': 0.572},
                    {'left': -1.123, 'top': -1.003, 'size': 3.21, 'bgLeft': -0.068, 'bgTop': 0.157, 'bgSize': 0.693},
                    {'left': -1.123, 'top': -1.003, 'size': 3.21, 'bgLeft': 0.342, 'bgTop': 0.157, 'bgSize': 0.693},
                    {'left': -1.123, 'top': -1.003, 'size': 3.21, 'bgLeft': 0.032, 'bgTop': 0.039, 'bgSize': 0.924}
                ],
            ]
        else:
            presets = [
                [{'left': -0.3}], [{'left': -0.3, 'layers': {'shadow': False}}],
                [{}], [{'layers': {'shadow': False}}],
                [{}, {}, {}], [{}, {}, {}, {}, {}],
            ]
        return presets

    def get_layers(self):
        # Shown in proper drawing order
        if self.slug == 'bottle':
            layers = [
                {'layer': 'base_shadow', 'mode': 'source-over', 'file': 'base_shadow.png', 'background': True},
                {'layer': 'bottle', 'mode': 'source-over', 'file': 'bottle.png', 'background': True},
                {'layer': 'mask', 'mode': 'source-over', 'file': 'bottle_mask.png'},
                {'layer': 'label', 'mode': 'source-in', 'saveSize': 1000},
                {'layer': 'shadow', 'mode': 'multiply', 'file': 'bottle_shadows.png'},
                {'layer': 'light', 'mode': 'screen', 'file': 'bottle_highlights.png'},
            ]
        elif self.slug == 'container':
            layers = [
                {'layer': 'container', 'mode': 'source-over', 'file': 'container.png'},
                {'layer': 'mask', 'mode': 'multiply', 'file': 'mask.png'},
                {'layer': 'label', 'mode': 'multiply', 'saveSize': 860, 'position': {
                    'top': 0.3186, 'left': 0.1767, 'right': 0.6465, 'bottom': 0.5023
                }},
                {'layer': 'shadow', 'mode': 'source-over', 'file': 'shadow.png'},
                {'layer': 'light', 'mode': 'screen', 'file': 'reflections.png'},
            ]
        elif self.slug == 'tincture':
            layers = [
                {'layer': 'bottle', 'mode': 'source-over', 'file': 'tincture_bottle_30.png', 'background': True},
                {'layer': 'shadow', 'mode': 'source-over', 'file': 'shadows_30.png', 'background': True},
                {'layer': 'mask', 'mode': 'source-over', 'file': 'mask_30.png'},
                {'layer': 'label', 'mode': 'source-atop', 'saveSize': 900},
                {'layer': 'dark', 'mode': 'multiply', 'file': 'darken_30.png'},
                {'layer': 'light', 'mode': 'screen', 'file': 'reflections_30.png'},
            ]
        elif self.slug == '4oz-bottle':
            layers = [
                {'layer': 'shadow', 'mode': 'source-over', 'file': 'shadow.png', 'background': True},
                {'layer': 'bottle', 'mode': 'source-over', 'file': 'bottle.png', 'background': True},
                {'layer': 'light', 'mode': 'screen', 'file': 'refractions.png', 'background': True},
                {'layer': 'mask', 'mode': 'source-over', 'file': 'mask.png'},
                {'layer': 'label', 'mode': 'source-atop', 'saveSize': 1000},
                {'combined': ['mask'], 'layer': 'light2', 'mode': 'screen', 'file': 'refractions.png'},
            ]
        elif 'colored-container-' in self.slug:
            container_file = f"container-{self.slug.replace('colored-container-', '')}-gummy.png"
            layers = [
                {'layer': 'container', 'mode': 'source-over', 'file': container_file, 'background': True},
                {'layer': 'shadow', 'mode': 'source-over', 'file': 'shadow.png', 'background': True},
                {'layer': 'light', 'mode': 'screen', 'file': 'refractions.png', 'background': True},
                {'layer': 'mask', 'mode': 'source-over', 'file': 'mask.png'},
                {'layer': 'label', 'mode': 'source-atop', 'saveSize': 1500},
                {'combined': ['mask'], 'layer': 'shadow2', 'mode': 'source-over', 'file': 'shadow.png'},
                {'combined': ['mask'], 'layer': 'light2', 'mode': 'screen', 'file': 'refractions.png'},
            ]
        elif self.slug == '2500cc-powder-container':
            layers = [
                {'layer': 'shadow', 'mode': 'source-over', 'file': 'shadow.png', 'background': True},
                {'layer': 'container', 'mode': 'source-over', 'file': 'bottle.png', 'background': True},
                {'layer': 'mask', 'mode': 'source-over', 'file': 'mask.png'},
                {'layer': 'label', 'mode': 'source-atop', 'saveSize': 1000},
                {'layer': 'light', 'mode': 'source-over', 'file': 'refractions.png'},
            ]
        elif self.slug in ['sour-gummies-bottle', 'cdb-gummies']:
            layers = [
                {'layer': 'container', 'mode': 'source-over', 'file': 'bottle.png', 'background': True},
                {'layer': 'mask', 'mode': 'source-over', 'file': 'mask.png'},
                {'layer': 'label', 'mode': 'source-atop', 'saveSize': 1000},
                {'layer': 'light', 'mode': 'screen', 'file': 'refractions.png'},
            ]
        elif self.slug == '2oz-pump-bottle':
            layers = [
                {'layer': 'bottle', 'mode': 'source-over', 'file': 'bottle.png', 'background': True},
                {'layer': 'shadow', 'mode': 'multiply', 'file': 'shadow.png', 'background': True},
                {'layer': 'light', 'mode': 'source-over', 'file': 'refractions.png', 'background': True},
                {'layer': 'mask', 'mode': 'source-over', 'file': 'mask.png'},
                {'layer': 'label', 'mode': 'source-atop', 'saveSize': 1000},
                {'combined': ['mask'], 'layer': 'light2', 'mode': 'source-over', 'file': 'refractions.png'},
            ]
        elif self.slug == '4oz-cosmetic-jar':
            layers = [
                {'layer': 'shadow', 'mode': 'source-over', 'file': 'shadow.png', 'background': True},
                {'layer': 'jar', 'mode': 'source-over', 'file': 'jar.png', 'background': True},
                {'layer': 'backlight', 'mode': 'screen', 'file': 'refractions.png', 'background': True},
                {'layer': 'mask', 'mode': 'source-over', 'file': 'mask.png'},
                {'layer': 'label', 'mode': 'source-atop', 'saveSize': 1000},
                {'combined': ['mask'], 'layer': 'light', 'mode': 'screen', 'file': 'refractions.png'},
            ]
        elif self.slug == 'exfoliating-cleanser':
            layers = [
                {'layer': 'shadow', 'mode': 'source-over', 'file': 'shadow.png', 'background': True},
                {'layer': 'bottle', 'mode': 'source-over', 'file': 'bottle.png', 'background': True},
                {'layer': 'light', 'mode': 'screen', 'file': 'refractions.png', 'background': True},
                {'layer': 'mask', 'mode': 'source-over', 'file': 'mask.png'},
                {'layer': 'label', 'mode': 'source-atop', 'saveSize': 1000},
                {'combined': ['mask'], 'layer': 'light2', 'mode': 'screen', 'file': 'refractions.png'},
            ]
        elif self.slug == '1oz-pump-bottle':
            layers = [
                {'layer': 'shadow', 'mode': 'source-over', 'file': 'shadow.png', 'background': True},
                {'layer': 'bottle', 'mode': 'source-over', 'file': 'bottle.png', 'background': True},
                {'layer': 'light', 'mode': 'screen', 'file': 'refractions.png', 'background': True},
                {'layer': 'mask', 'mode': 'source-over', 'file': 'mask.png'},
                {'layer': 'label', 'mode': 'source-atop', 'saveSize': 1000},
                {'layer': 'light', 'mode': 'screen', 'file': 'refractions.png'},
            ]
        elif self.slug == '4oz-pump-bottle':
            layers = [
                {'layer': 'bottle', 'mode': 'source-over', 'file': 'bottle.png', 'background': True},
                {'layer': 'shadow', 'mode': 'source-over', 'file': 'shadow.png', 'background': True},
                {'layer': 'light', 'mode': 'screen', 'file': 'highlight.png', 'background': True},
                {'layer': 'bottle', 'mode': 'source-over', 'file': 'bottle.png'},
                {'layer': 'label', 'mode': 'source-over', 'saveSize': 1000},
                {'layer': 'shadow', 'mode': 'source-over', 'file': 'shadow.png'},
                {'layer': 'light2', 'mode': 'screen', 'file': 'highlight.png'},
                {'layer': 'mask', 'mode': 'destination-in', 'file': 'mask.png'},
            ]
        elif self.slug in ['44oz-jar-black-lid', '32oz-jar-black-lid', '16oz-jar-black-lid']:
            layers = [
                {'layer': 'shadow', 'mode': 'source-over', 'file': 'shadow.png', 'background': True},
                {'layer': 'container', 'mode': 'source-over', 'file': 'container.png', 'background': True},
                {'layer': 'refraction', 'mode': 'screen', 'file': 'refraction.png', 'background': True},
                {'layer': 'container2', 'mode': 'source-over', 'file': 'container.png'},
                {'layer': 'label', 'mode': 'source-over', 'saveSize': 1000},
                {'layer': 'refraction2', 'mode': 'screen', 'file': 'refraction.png'},
                {'layer': 'mask', 'mode': 'destination-in', 'file': 'mask.png'},
            ]
        elif self.slug == '4oz-jar':
            layers = [
                {'layer': 'jar', 'mode': 'source-over', 'file': 'jar.png', 'background': True},
                {'layer': 'light', 'mode': 'screen', 'file': 'reflections.png', 'background': True},
                {'layer': 'jar', 'mode': 'source-over', 'file': 'jar.png'},
                {'layer': 'label', 'mode': 'multiply', 'saveSize': 1000},
                {'layer': 'shadow', 'mode': 'source-over', 'file': 'shadow.png'},
                {'layer': 'light', 'mode': 'screen', 'file': 'reflections.png'},
                {'layer': 'mask', 'mode': 'destination-in', 'file': 'mask.png'},
            ]
        elif self.slug == '8oz-bottle':
            layers = [
                {'layer': 'shadow', 'mode': 'source-over', 'file': 'shadow.png', 'background': True},
                {'layer': 'jar', 'mode': 'source-over', 'file': 'bottle.png', 'background': True},
                {'layer': 'jar', 'mode': 'source-over', 'file': 'bottle.png'},
                {'layer': 'label', 'mode': 'multiply', 'saveSize': 1000},
                {'layer': 'light', 'mode': 'screen', 'file': 'refractions.png'},
                {'layer': 'mask', 'mode': 'destination-in', 'file': 'mask.png'},
            ]
        elif self.slug == '20oz-black-jar':
            layers = [
                {'layer': 'shadow', 'mode': 'source-over', 'file': 'shadow.png', 'background': True},
                {'layer': 'jar', 'mode': 'source-over', 'file': 'jar.png', 'background': True},
                {'layer': 'jar', 'mode': 'source-over', 'file': 'jar.png'},
                {'layer': 'label', 'mode': 'multiply', 'saveSize': 1000},
                {'layer': 'light', 'mode': 'screen', 'file': 'refractions.png'},
                {'layer': 'mask', 'mode': 'destination-in', 'file': 'mask.png'},
            ]
        elif self.slug == 'coffee-bag':
            layers = [
                {'layer': 'bag', 'mode': 'source-over', 'file': 'bag.png', 'background': True},
                {'layer': 'shadow', 'mode': 'source-over', 'file': 'shadow.png', 'background': True},
                {'layer': 'light', 'mode': 'multiply', 'file': 'refractions.png', 'background': True},
                {'layer': 'mask', 'mode': 'source-over', 'file': 'mask.png'},
                {'layer': 'label', 'mode': 'source-atop', 'saveSize': 1500},
                {'combined': ['mask'], 'layer': 'light2', 'mode': 'multiply', 'file': 'refractions.png'},
            ]
        else:
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
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    description = models.TextField()
    fee = models.DecimalField(max_digits=10, decimal_places=2)
    transaction_id = models.CharField(max_length=255, null=True)
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
