from django.db import models
from django.contrib.auth.models import User

from leadgalaxy.models import (
    ShopifyStore,
    ShopifyProduct,
    ShopifyOrderTrack
)

SYNC_STATUS = (
    (0, 'Pending'),
    (1, 'Started'),
    (2, 'Completed'),
    (3, 'Unauthorized'),
    (4, 'Error'),
    (5, 'Disabled'),
)


class ShopifySyncStatus(models.Model):
    store = models.ForeignKey(ShopifyStore)
    sync_type = models.CharField(max_length=32)
    sync_status = models.IntegerField(default=0, choices=SYNC_STATUS)
    orders_count = models.IntegerField(default=0)
    pending_orders = models.TextField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __unicode__(self):
        return u'{} / {}'.format(self.sync_type, self.store.title)

    def add_pending_order(self, order_id, commit=True):
        try:
            pending_orders = self.pending_orders.split(',')
        except:
            pending_orders = []

        order_id = str(order_id)
        if order_id not in pending_orders:
            pending_orders.append(order_id)
            self.pending_orders = ','.join(pending_orders)

            if commit:
                self.save()

    def pop_pending_orders(self, commit=True):
        try:
            pending_orders = self.pending_orders.split(',')
        except:
            pending_orders = []

        if len(pending_orders):
            order = pending_orders.pop()
            self.pending_orders = ','.join(pending_orders)
        else:
            order = None

        if commit:
            self.save()

        return order


class ShopifyOrder(models.Model):
    class Meta:
        unique_together = ('store', 'order_id')

    user = models.ForeignKey(User)
    store = models.ForeignKey(ShopifyStore)

    order_id = models.BigIntegerField()
    order_number = models.IntegerField()
    total_price = models.FloatField()

    customer_id = models.BigIntegerField()
    customer_name = models.CharField(max_length=256, blank=True, null=True, default='')
    customer_email = models.CharField(max_length=256, blank=True, null=True, default='')

    financial_status = models.CharField(max_length=32, blank=True, null=True, default='')
    fulfillment_status = models.CharField(max_length=32, blank=True, null=True, default='')

    note = models.TextField(blank=True, null=True,  default='')
    tags = models.TextField(blank=True, null=True, default='')
    city = models.CharField(max_length=64, blank=True, null=True, default='')
    zip_code = models.CharField(max_length=32, blank=True, null=True, default='')
    country_code = models.CharField(max_length=32, blank=True, null=True, default='')
    items_count = models.IntegerField(blank=True, null=True, verbose_name='Item Lines count')

    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()
    closed_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)

    def __unicode__(self):
        return u'#{} | {}'.format(self.order_number + 1000, self.store.title)


class ShopifyOrderLine(models.Model):
    class Meta:
        unique_together = ('order', 'line_id')

    order = models.ForeignKey(ShopifyOrder)
    product = models.ForeignKey(ShopifyProduct, null=True, on_delete=models.deletion.SET_NULL)
    track = models.ForeignKey(ShopifyOrderTrack, null=True, on_delete=models.deletion.SET_NULL)

    line_id = models.BigIntegerField()
    shopify_product = models.BigIntegerField()
    title = models.TextField(blank=True, null=True, default='')
    price = models.FloatField()
    quantity = models.IntegerField()
    fulfillment_status = models.TextField(blank=True, null=True)

    variant_id = models.BigIntegerField()
    variant_title = models.TextField(blank=True, null=True, default='')

    def __unicode__(self):
        return u'{}'.format(self.variant_title)


class ShopifyOrderShippingLine(models.Model):
    store = models.ForeignKey(ShopifyStore)
    order = models.ForeignKey(ShopifyOrder, related_name='shipping_lines')
    shipping_line_id = models.BigIntegerField()
    price = models.FloatField()
    title = models.CharField(max_length=256, db_index=True)
    code = models.CharField(max_length=256)
    source = models.CharField(max_length=256)
    phone = models.CharField(max_length=256, null=True, blank=True)
    carrier_identifier = models.CharField(max_length=256, null=True, blank=True)
    requested_fulfillment_service_id = models.CharField(max_length=256, null=True, blank=True)

    def __unicode__(self):
        return self.title
