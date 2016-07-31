from django.db import models

from leadgalaxy.models import ShopifyStore, ShopifyProduct, AliexpressProductChange


class ProductRevision(models.Model):
     store = models.ForeignKey(ShopifyStore)
     product = models.ForeignKey(ShopifyProduct)
     product_change = models.ForeignKey(AliexpressProductChange)
     
     shopify_id = models.BigIntegerField(default=0)
     data = models.TextField(default='', blank=True)

     created_at = models.DateTimeField(auto_now=True)

