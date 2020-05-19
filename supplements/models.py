from django.contrib.auth.models import User
from django.db import models

from product_common import models as model_base

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
import simplejson as json

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
    current_label = models.OneToOneField('UserSupplementLabel',
                                         on_delete=models.SET_NULL,
                                         related_name='current_label_of',
                                         null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    is_deleted = models.BooleanField(default=False, blank=True)

    def __str__(self):
        return self.title

    def get_weight(self, quantity):
        return self.pl_supplement.weight * quantity


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


class PLSOrderLine(PLSOrderLineMixin, model_base.AbstractOrderLine):
    """
    Adding store_type, store_id, and order_id here so that we can run exists
    query atomically.
    """
    class Meta:
        unique_together = ['store_type',
                           'store_id',
                           'store_order_id',
                           'line_id']

    is_label_printed = models.BooleanField(default=False)
    sale_price = models.IntegerField()
    wholesale_price = models.IntegerField()

    label = models.ForeignKey(UserSupplementLabel,
                              on_delete=models.SET_NULL,
                              null=True,
                              related_name='orders')

    pls_order = models.ForeignKey(PLSOrder,
                                  on_delete=models.CASCADE,
                                  related_name='order_items',
                                  null=True)


class Payout(PayoutMixin, model_base.AbstractPayout):
    pass


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
        return f'{self.height.normalize()}×{self.width.normalize()}'


class MockupType(models.Model):
    slug = models.SlugField(max_length=100)
    name = models.CharField(max_length=255)

    def __str__(self):
        return self.name
