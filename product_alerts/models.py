from django.db import models
from django.contrib.auth.models import User

from leadgalaxy.models import ShopifyProduct
from commercehq_core.models import CommerceHQProduct

PRODUCT_CHANGE_STATUS_CHOICES = (
    (0, 'Pending'),
    (1, 'Applied'),
    (2, 'Failed'),
)


class ProductChange(models.Model):
    class Meta:
        ordering = ['-updated_at']
        index_together = ['user', 'seen', 'hidden']

    user = models.ForeignKey(User, null=True)
    shopify_product = models.ForeignKey(ShopifyProduct, null=True)
    chq_product = models.ForeignKey(CommerceHQProduct, null=True)
    store_type = models.CharField(max_length=255, blank=True, default='shopify')
    data = models.TextField(blank=True, default='')
    hidden = models.BooleanField(default=False, verbose_name='Archived change')
    seen = models.BooleanField(default=False, verbose_name='User viewed the changes')
    status = models.IntegerField(default=0, choices=PRODUCT_CHANGE_STATUS_CHOICES)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    notified_at = models.DateTimeField(null=True, verbose_name='Email Notification Sate')

    def __unicode__(self):
        return u'{}'.format(self.id)

    def orders_count(self, open=True):
        if self.store_type == 'shopify':
            return self.shopify_product.shopifyorderline_set \
                       .exclude(order__fulfillment_status='fulfilled') \
                       .filter(order__closed_at=None, order__cancelled_at=None) \
                       .count()
        return 0

    @property
    def product(self):
        if self.store_type == 'shopify':
            return self.shopify_product
        if self.store_type == 'chq':
            return self.chq_product
        return None
