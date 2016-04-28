from django.db import models
from django.contrib.auth.models import User

from leadgalaxy.models import ShopifyStore, ShopifyProduct

SYNC_STATUS = (
    (0, 'Pending'),
    (1, 'Started'),
    (2, 'Completed'),
    (3, 'Unauthorized'),
    (4, 'Error'),
)


class ShopifySyncStatus(models.Model):
    store = models.ForeignKey(ShopifyStore)
    sync_type = models.CharField(max_length=32)
    sync_status = models.IntegerField(default=0, choices=SYNC_STATUS)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __unicode__(self):
        return u'{} / {}'.format(self.sync_type, self.store)


class ShopifyOrder(models.Model):
    class Meta:
        unique_together = ('store', 'order_id')

    user = models.ForeignKey(User, related_name='user')
    store = models.ForeignKey(ShopifyStore, related_name='store')

    order_id = models.BigIntegerField()
    order_number = models.IntegerField()
    total_price = models.FloatField()

    customer_id = models.BigIntegerField()
    customer_name = models.CharField(max_length=256, blank=True, null=True, default='')
    customer_email = models.CharField(max_length=256, blank=True, null=True, default='')

    financial_status = models.CharField(max_length=32, blank=True, default='')
    fulfillment_status = models.CharField(max_length=32, blank=True, null=True, default='')

    note = models.TextField(blank=True, null=True,  default='')
    tags = models.CharField(max_length=256, blank=True, null=True, default='')
    city = models.CharField(max_length=64, blank=True, default='')
    zip_code = models.CharField(max_length=32, blank=True, default='')
    country_code = models.CharField(max_length=32, blank=True, default='')

    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()
    closed_at = models.DateTimeField(null=True, blank=True)

    def __unicode__(self):
        return u'#{}'.format(self.order_number)


class ShopifyOrderLine(models.Model):
    class Meta:
        unique_together = ('order', 'line_id')

    order = models.ForeignKey(ShopifyOrder)
    product = models.ForeignKey(ShopifyProduct, null=True)

    line_id = models.BigIntegerField()
    shopify_product = models.BigIntegerField()
    title = models.CharField(max_length=256, blank=True, default='')
    price = models.FloatField()
    quantity = models.IntegerField()

    variant_id = models.BigIntegerField()
    variant_title = models.CharField(max_length=64, blank=True, default='')

    def __unicode__(self):
        return u'{}'.format(self.variant_title)
