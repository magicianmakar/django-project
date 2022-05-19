import json

from django.contrib.auth.models import User
from django.db import models

from shopified_core.models import BoardBase, OrderTrackBase, ProductBase, StoreBase, SupplierBase, UserUploadBase
from shopified_core.utils import hash_url_filename, safe_str


class FBMarketplaceStore(StoreBase):
    class Meta(StoreBase.Meta):
        verbose_name = 'Facebook Marketplace Store'
        ordering = ['-created_at']

    title = models.CharField(max_length=512, blank=True, default='')
    is_active = models.BooleanField(default=True, db_index=True)

    user = models.ForeignKey(User, on_delete=models.CASCADE)

    uninstall_reason = models.TextField(null=True, blank=True)
    uninstalled_at = models.DateTimeField(null=True, blank=True)
    delete_request_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title

    def get_admin_url(self, *args):
        return 'https://facebook.com/marketplace/create/item'


class FBMarketplaceProduct(ProductBase):
    class Meta(ProductBase.Meta):
        verbose_name = 'Facebook Marketplace Product'
        ordering = ['-created_at']

    store = models.ForeignKey('FBMarketplaceStore', related_name='products', null=True, on_delete=models.CASCADE)

    source_id = models.BigIntegerField(default=0, null=True, blank=True, db_index=True, verbose_name='Facebook Marketplace Product ID')
    default_supplier = models.ForeignKey('FBMarketplaceSupplier', on_delete=models.SET_NULL, null=True, blank=True)

    parent_product = models.ForeignKey('FBMarketplaceProduct', on_delete=models.SET_NULL, null=True, blank=True, verbose_name='Duplicate of product')

    def __str__(self):
        return f'<FBMarketplace Product: {self.id}>'

    def save(self, *args, **kwargs):
        data = json.loads(self.data)

        self.title = data.get('title', '')
        self.tags = safe_str(data.get('tags', ''))[:1024]
        self.product_type = safe_str(data.get('type', ''))[:254]

        try:
            self.price = '%.02f' % float(data['price'])
        except:
            self.price = 0.0

        super(FBMarketplaceProduct, self).save(*args, **kwargs)

    @property
    def parsed(self):
        try:
            return json.loads(self.data)
        except:
            return {}

    @property
    def is_connected(self):
        return bool(self.get_marketplace_id())

    @property
    def boards(self):
        return self.fbmarketplaceboard_set

    @property
    def fb_marketplace_url(self):
        if self.is_connected:
            return f'https://web.facebook.com/marketplace/item/{self.source_id}'
        else:
            return None

    def have_supplier(self):
        try:
            return self.default_supplier is not None
        except:
            return False

    def get_marketplace_id(self):
        return self.source_id if self.store else None

    def get_product(self):
        try:
            return json.loads(self.data)['title']
        except:
            return None

    def update_data(self, data):
        if type(data) is not dict:
            data = json.loads(data)

        try:
            product_data = json.loads(self.data)
        except:
            product_data = {}

        product_data.update(data)

        self.data = json.dumps(product_data)

    def set_default_supplier(self, supplier, commit=False):
        self.default_supplier = supplier

        if commit:
            self.save()

        self.get_suppliers().update(is_default=False)

        supplier.is_default = True
        supplier.save()

    def get_suppliers(self):
        return self.fbmarketplacesupplier_set.all().order_by('-is_default')

    def get_common_images(self):
        common_images = set()
        image_urls = self.parsed.get('images', [])

        if not self.source_id:
            hashed_variant_images = list(self.parsed.get('variants_images', {}).keys())

            for image_url in image_urls:
                if hash_url_filename(image_url) not in hashed_variant_images:
                    common_images.add(image_url)
        else:
            variant_primary_images = []
            variants = self.parsed.get('variants', [])

            for variant in variants:
                images = variant.get('images', [])

                for i, image in enumerate(images):
                    if i == 0:
                        variant_primary_images.append(image['path'])
                    else:
                        common_images.add(image['path'])

            if len(set(variant_primary_images)) == 1:
                # variants are using one common image
                common_images.update(set(image_urls) | set(variant_primary_images))
            else:
                common_images.update(set(image_urls) - set(variant_primary_images))

        return list(common_images)

    def get_image(self):
        images = self.parsed.get('images', [])

        if images:
            return images[0]

        common_images = self.get_common_images()

        if common_images:
            return common_images[0]

        variants = self.parsed.get('variants', [])
        variant_images = []
        for variant in variants:
            for image in variant.get('images', []):
                variant_images.append(image.get('path'))

        return variant_images[0] if variant_images else ''


class FBMarketplaceSupplier(SupplierBase):
    store = models.ForeignKey('FBMarketplaceStore', null=True, related_name='suppliers', on_delete=models.CASCADE)
    product = models.ForeignKey('FBMarketplaceProduct', on_delete=models.CASCADE)

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
            return '<FBMarketplaceSupplier: {}>'.format(self.id)


class FBMarketplaceOrderTrack(OrderTrackBase):
    CUSTOM_TRACKING_KEY = 'fb_marketplace_custom_tracking'

    store = models.ForeignKey(FBMarketplaceStore, null=True, on_delete=models.CASCADE)
    product_id = models.BigIntegerField()
    fb_marketplace_status = models.CharField(max_length=128,
                                             blank=True,
                                             null=True,
                                             default='',
                                             verbose_name="Facebook Marketplace Fulfillment Status")

    def __str__(self):
        return f'<FBMarketplaceOrderTrack: {self.id}>'


class FBMarketplaceBoard(BoardBase):
    products = models.ManyToManyField('FBMarketplaceProduct', blank=True)

    def __str__(self):
        return f'<FBMarketplaceBoard: {self.id}>'


class FBMarketplaceUserUpload(UserUploadBase):
    product = models.ForeignKey(FBMarketplaceProduct, null=True, on_delete=models.CASCADE)
