import json

from django.contrib.auth.models import User
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.urls import reverse

from shopified_core.models import SupplierBase
from shopified_core.utils import hash_url_filename


class MasterProduct(models.Model):
    class Meta:
        verbose_name = 'Master Product'
        ordering = ['-created_at']

    user = models.ForeignKey(User, on_delete=models.CASCADE)

    title = models.TextField(blank=True, null=True, db_index=True)
    description = models.TextField(blank=True, null=True)
    price = models.FloatField(default=0.0)

    compare_at_price = models.DecimalField(decimal_places=2, max_digits=9, blank=True, null=True)
    images = models.TextField(default='[]')
    product_type = models.CharField(max_length=255, blank=True, default='')
    tags = models.TextField(blank=True, null=True, default='')
    notes = models.TextField(blank=True, null=True, default='')

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    extension_data = models.TextField(blank=True, null=True, default='{}')
    variants_config = models.TextField(blank=True, null=True, default='{}')

    original_url = models.TextField(blank=True, null=True)
    vendor = models.TextField(blank=True, null=True)
    published = models.BooleanField(default=False)

    default_supplier = models.ForeignKey('MasterProductSupplier', on_delete=models.SET_NULL, null=True, blank=True)

    def __str__(self):
        return f'<MasterProduct: {self.id}>'

    def update_extension_data(self, data):
        if type(data) is not dict:
            data = json.loads(data)

        try:
            product_data = json.loads(self.extension_data)
        except:
            product_data = {}

        product_data.update(data)

        self.extension_data = json.dumps(product_data)

    @property
    def media_links(self):
        try:
            images = json.loads(self.images)
        except:
            images = []

        return images

    @property
    def url(self):
        return reverse('multichannel:product_detail', kwargs={'pk': self.id})

    @property
    def parsed(self):
        try:
            data = json.loads(self.extension_data)

            if type(data['images']) is dict:
                data['images'] = list(data['images'].values())

            return data

        except:
            return {}

    @property
    def variants_data(self):
        try:
            product_images = json.loads(self.images)
            variants_config = json.loads(self.variants_config)
            variants_info = variants_config.get('variants_info')
            variants_images = variants_config.get('variants_images')

            data = []
            for key in variants_info.keys():
                positions = [i for i, x in enumerate(list(variants_images.values())) if x in key]
                hashed_image = ''
                if positions:
                    hashed_image = list(variants_images.keys())[positions[0]]
                for product_image in product_images:
                    if hash_url_filename(product_image) == hashed_image:
                        variants_info[key]['image'] = product_image
                data.append(dict(title=key, **variants_info[key]))
        except:
            data = []

        return data

    def get_suppliers(self):
        return self.masterproductsupplier_set.all().order_by('-is_default')

    def set_default_supplier(self, supplier, commit=False):
        self.default_supplier = supplier

        if commit:
            self.save()

        self.get_suppliers().update(is_default=False)

        supplier.is_default = True
        supplier.save()

    def get_variants_titles(self):
        return [variant['title'] for variant in self.variants_data]


class MasterProductSupplier(SupplierBase):
    product = models.ForeignKey('MasterProduct', on_delete=models.CASCADE)

    product_url = models.CharField(max_length=512, null=True, blank=True)
    supplier_name = models.CharField(max_length=512, null=True, blank=True, db_index=True)
    supplier_url = models.CharField(max_length=512, null=True, blank=True)
    shipping_method = models.CharField(max_length=512, null=True, blank=True)
    variants_map = models.TextField(null=True, blank=True)
    is_default = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        if self.supplier_name:
            return self.supplier_name
        elif self.supplier_url:
            return self.supplier_url
        else:
            return '<MasterProductSupplier: {}>'.format(self.id)


class ProductTemplate(models.Model):
    TITLE_AND_DESCRIPTION = 'title_and_description'
    PRICING = 'pricing'
    TYPE_CHOICES = [(TITLE_AND_DESCRIPTION, 'Title & Description'), (PRICING, 'Pricing')]
    INACTIVE = 'inactive'
    ACTIVE_OVERRIDE = 'active_override'
    ACTIVE_CALCULATED = 'active_calculated'
    STATUS_CHOICES = [(INACTIVE, 'Inactive'), (ACTIVE_OVERRIDE, 'Active Override'),
                      (ACTIVE_CALCULATED, 'Active Calculated')]

    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    store = GenericForeignKey('content_type', 'object_id')

    type = models.CharField(max_length=32, choices=TYPE_CHOICES, default=TITLE_AND_DESCRIPTION)
    name = models.CharField(max_length=255, null=False, blank=False, default='Template Name')

    title = models.TextField(null=True, blank=True, default='{{ title }}')
    description = models.TextField(null=True, blank=True, default='{{ description }}')

    price_override_amount = models.DecimalField(decimal_places=2, max_digits=10, default=0.00, null=True, blank=True)
    price_modifier = models.CharField(max_length=1, choices=[('$', '$'), ('%', '%')], default='$')
    price_direction = models.CharField(max_length=1, choices=[('+', '+'), ('-', '-')], default='+')
    price_amount = models.DecimalField(decimal_places=2, max_digits=10, default=0.00, null=True, blank=True)
    price_status = models.CharField(max_length=32, choices=STATUS_CHOICES, default=INACTIVE)

    compare_price_override_amount = models.DecimalField(decimal_places=2, max_digits=10, default=0.00,
                                                        null=True, blank=True)
    compare_price_modifier = models.CharField(max_length=1, choices=[('$', '$'), ('%', '%')], default='$')
    compare_price_direction = models.CharField(max_length=1, choices=[('+', '+'), ('-', '-')], default='+')
    compare_price_amount = models.DecimalField(decimal_places=2, max_digits=10, default=0.00, null=True, blank=True)
    compare_price_status = models.CharField(max_length=32, choices=STATUS_CHOICES, default=INACTIVE)

    is_active = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('created_at',)

    def __str__(self):
        return self.name
