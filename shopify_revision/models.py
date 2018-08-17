from django.db import models

from leadgalaxy.models import ShopifyStore, ShopifyProduct, AliexpressProductChange


class ProductRevision(models.Model):
    store = models.ForeignKey(ShopifyStore, null=True, blank=True, on_delete=models.CASCADE)
    product = models.ForeignKey(ShopifyProduct, on_delete=models.CASCADE)
    product_change = models.ForeignKey(AliexpressProductChange, on_delete=models.CASCADE)

    shopify_id = models.BigIntegerField(default=0)
    data = models.TextField(default='', blank=True)

    created_at = models.DateTimeField(auto_now=True)
