from django.contrib.auth.models import User
from django.db import models

from leadgalaxy.models import ShopifyStore


class FacebookAccess(models.Model):
    user = models.ForeignKey(User)
    access_token = models.CharField(max_length=255)


class FacebookAccount(models.Model):
    access = models.ForeignKey(FacebookAccess, related_name='accounts')
    last_sync = models.DateField(null=True)
    account_id = models.CharField(max_length=50)
    account_name = models.CharField(max_length=255)


class FacebookInsight(models.Model):
    account = models.ForeignKey(FacebookAccount,
                                related_name='insights',
                                on_delete=models.CASCADE)
    date = models.DateField()
    impressions = models.IntegerField(default=0)
    spend = models.DecimalField(decimal_places=2, max_digits=9)

    class Meta:
        ordering = ['date']


class ShopifyProfit(models.Model):
    store = models.ForeignKey(ShopifyStore)
    date = models.DateField()
    revenue = models.DecimalField(decimal_places=2, max_digits=9, default=0)
    fulfillment_cost = models.DecimalField(decimal_places=2, max_digits=9, default=0)
    other_costs = models.DecimalField(decimal_places=2, max_digits=9, default=0)

    class Meta:
        ordering = ['date']


class ShopifyProfitImportedOrder(models.Model):
    profit = models.ForeignKey(ShopifyProfit, related_name='imported_orders')
    order_id = models.BigIntegerField()


class ShopifyProfitImportedOrderTrack(models.Model):
    profit = models.ForeignKey(ShopifyProfit, related_name='imported_order_tracks')
    order_id = models.BigIntegerField()
    source_id = models.CharField(max_length=512, blank=True, default='')
    amount = models.DecimalField(decimal_places=2, max_digits=9, default=0)
