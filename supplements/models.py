import base64
from io import BytesIO

from PIL import Image
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
    label_presets = models.TextField(default='{}', blank=True)
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
        else:
            presets = []
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
                }, 'file': 'DROP_80013_AntiWrinkleCream_BroadSpec_4oz_OUTLINED.jpg'},
                {'layer': 'shadow', 'mode': 'source-over', 'file': 'shadow.png'},
                {'layer': 'light', 'mode': 'screen', 'file': 'reflections.png'},
            ]
        elif self.slug == 'tincture':
            layers = [
                {'layer': 'bottle', 'mode': 'source-over', 'file': 'tincture_bottle_30.png', 'background': True},
                {'layer': 'shadow', 'mode': 'source-over', 'file': 'shadows_30.png', 'background': True},
                {'layer': 'mask', 'mode': 'source-over', 'file': 'mask_30.png'},
                {'layer': 'label', 'mode': 'source-in', 'saveSize': 900, 'file': 'DROP_80001_HempOil_500mg_1oz_OUTLINED.jpg'},
                {'layer': 'dark', 'mode': 'multiply', 'file': 'darken_30.png'},
                {'layer': 'light', 'mode': 'screen', 'file': 'reflections_30.png'},
            ]
        else:
            layers = []

        for layer in layers:
            if not layer.get('file'):
                continue

            image = Image.open(f"app/static/pls-mockup/{self.slug}/{layer['file']}")
            raw_image = BytesIO()
            ext = layer['file'].split('.')[-1]  # From PIL.Image.SAVE
            ext = {'jpg': 'jpeg'}.get(ext, ext)
            image.save(raw_image, format=ext)
            raw_image.seek(0)
            raw_image.name = layer['file']

            image_data = base64.b64encode(raw_image.getvalue()).decode()
            layer['file'] = f'data:image/{ext};base64,{image_data}'

        return layers
