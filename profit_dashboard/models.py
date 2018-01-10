from django.contrib.auth.models import User
from django.db import models

from leadgalaxy.models import ShopifyStore


CONFIG_CHOICES = (
    ('include', 'Include Selected Campaign Only'),
    ('include_and_new', 'Include Selected Campaign and newer ones'),
    ('exclude', 'Exclude Selected Campaign')
)


class FacebookAccess(models.Model):
    user = models.ForeignKey(User)
    store = models.ForeignKey(ShopifyStore, null=True)

    access_token = models.CharField(max_length=255)
    account_ids = models.CharField(max_length=255, null=True, blank=True)
    campaigns = models.TextField(null=True, blank=True)


class FacebookAccount(models.Model):
    access = models.ForeignKey(FacebookAccess, related_name='accounts')
    store = models.ForeignKey(ShopifyStore, null=True)

    last_sync = models.DateField(null=True)
    account_id = models.CharField(max_length=50)
    account_name = models.CharField(max_length=255)
    config = models.CharField(max_length=100, choices=CONFIG_CHOICES, default='selected')


class FacebookAdCost(models.Model):
    account = models.ForeignKey(FacebookAccount,
                                related_name='costs',
                                on_delete=models.CASCADE)
    created_at = models.DateField()
    impressions = models.IntegerField(default=0)
    spend = models.DecimalField(decimal_places=2, max_digits=9)

    class Meta:
        ordering = ['-created_at']


class AliexpressFulfillmentCost(models.Model):
    class Meta:
        ordering = ['-created_at']
        index_together = ['store', 'order_id', 'source_id']

    store = models.ForeignKey(ShopifyStore)
    order_id = models.BigIntegerField()
    source_id = models.CharField(max_length=512, blank=True, default='')

    created_at = models.DateField(db_index=True)

    shipping_cost = models.DecimalField(decimal_places=2, max_digits=9, default=0)
    products_cost = models.DecimalField(decimal_places=2, max_digits=9, default=0)
    total_cost = models.DecimalField(decimal_places=2, max_digits=9, default=0)


class OtherCost(models.Model):
    store = models.ForeignKey(ShopifyStore)
    date = models.DateField()
    amount = models.DecimalField(decimal_places=2, max_digits=9, default=0)

    class Meta:
        ordering = ['-date']
