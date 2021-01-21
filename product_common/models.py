from django.contrib.auth.models import User
from django.db import models

from .mixins import OrderLineMixin, OrderMixin, PayoutMixin, ProductMixin, SupplierMixin


class AbstractImage(models.Model):
    position = models.SmallIntegerField()
    image_url = models.URLField()

    class Meta:
        abstract = True


class Product(ProductMixin, models.Model):
    PRODUCT_TYPE = ''

    title = models.CharField(max_length=200)
    description = models.TextField()
    category = models.CharField(max_length=200)
    tags = models.TextField()
    shipstation_sku = models.CharField(max_length=20)

    cost_price = models.DecimalField(max_digits=10, decimal_places=2)
    product_type = models.CharField(max_length=20)
    supplier = models.ForeignKey('ProductSupplier',
                                 on_delete=models.SET_NULL,
                                 related_name='supplied_products',
                                 null=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title

    def to_dict(self):
        return dict(
            title=self.title,
            description=self.description,
            category=self.category,
            tags=self.tags,
            shipstation_sku=self.shipstation_sku,
            cost_price=self.cost_price,
            product_type=self.product_type,
            images=[i.to_dict() for i in self.images.all()],
        )


class ProductImage(AbstractImage):
    product = models.ForeignKey(Product,
                                on_delete=models.CASCADE,
                                related_name='images')

    def to_dict(self):
        return dict(
            position=self.position,
            image_url=self.image_url,
        )


class ProductSupplier(SupplierMixin, models.Model):
    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=100)
    profit_percentage = models.DecimalField(max_digits=10, decimal_places=2)
    is_shipping_supplier = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title


class AbstractOrderInfo(models.Model):
    SHOPIFY = 'shopify'
    CHQ = 'chq'
    WOO = 'woo'
    GEAR = 'gear'
    GKART = 'gkart'
    BIGCOMMERCE = 'bigcommerce'
    MYBASKET = 'mybasket'

    STORE_TYPES = [
        (SHOPIFY, 'Shopify'),
        (CHQ, 'CommerceHQ'),
        (WOO, 'WooCommerce'),
        (GEAR, 'GearBubble'),
        (GKART, 'GrooveKart'),
        (BIGCOMMERCE, 'BigCommerce'),
        (MYBASKET, 'MyBasket')
    ]

    store_type = models.CharField(max_length=15,
                                  choices=STORE_TYPES,
                                  default=SHOPIFY)

    # This will be the id of ShopifyStore, CommerceHQStore, WooStore, or
    # GearBubbleStore.
    store_id = models.IntegerField()

    store_order_id = models.CharField(max_length=50)

    class Meta:
        abstract = True


class AbstractOrder(AbstractOrderInfo, OrderMixin):
    class Meta:
        abstract = True

    PAID = 'paid'
    PENDING = 'pending'
    SHIPPED = 'shipped'

    STATUSES = [
        (PAID, 'Paid'),
        (PENDING, 'Pending'),
        (SHIPPED, 'Shipped'),
    ]

    order_number = models.CharField(max_length=50)
    stripe_transaction_id = models.CharField(max_length=50, blank=True)
    shipstation_key = models.CharField(max_length=500, blank=True, default='')

    amount = models.IntegerField(verbose_name='Total amount')
    status = models.CharField(max_length=10,
                              choices=STATUSES,
                              default=PENDING)
    user = models.ForeignKey(User,
                             on_delete=models.SET_NULL,
                             related_name='%(class)s_product_payments',
                             null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    payment_date = models.DateTimeField(null=True)
    is_fulfilled = models.BooleanField(default=False)


class Order(AbstractOrder):
    pass


class AbstractOrderLine(AbstractOrderInfo, OrderLineMixin):
    """
    Adding store_type, store_id, and order_id here so that we can run exists
    query atomically.
    """
    class Meta:
        abstract = True

    line_id = models.CharField(max_length=50)
    sku = models.CharField(max_length=50)
    shipstation_key = models.CharField(max_length=500)
    amount = models.IntegerField()
    quantity = models.IntegerField(default=1)
    tracking_number = models.CharField(max_length=128, blank=True, default='')

    created_at = models.DateTimeField(auto_now_add=True)


class OrderLine(AbstractOrderLine):
    class Meta:
        unique_together = ['store_type',
                           'store_id',
                           'store_order_id',
                           'line_id']

    order = models.ForeignKey(Order,
                              on_delete=models.CASCADE,
                              related_name='order_items',
                              null=True)


class AbstractPayout(models.Model, PayoutMixin):
    class Meta:
        abstract = True

    PAID = 'paid'
    PENDING = 'pending'

    STATUSES = [
        (PAID, 'Paid'),
        (PENDING, 'Pending'),
    ]

    reference_number = models.CharField(max_length=10)
    status = models.CharField(max_length=10,
                              choices=STATUSES,
                              default=PENDING)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.reference_number


class Payout(AbstractPayout):
    pass
