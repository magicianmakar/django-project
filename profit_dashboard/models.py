import arrow
import json
import requests

from django.contrib.auth.models import User
from django.conf import settings
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
    expires_in = models.DateTimeField(default=None, null=True, blank=True)
    account_ids = models.CharField(max_length=255, default='', blank=True)
    campaigns = models.TextField(default='', blank=True)

    def exchange_long_lived_token(self, new_access_token=None):
        """
        Exchange current access token for long lived one with +59 days expiration
        """
        # Renew only if token expires in less than 2 weeks
        delta_expires_in = self.expires_in - arrow.now().datetime
        if self.expires_in is not None and delta_expires_in.days > 14:
            return self.access_token

        if new_access_token is not None:
            self.access_token = new_access_token

        # Token exchange must be done manually for now
        url = 'https://graph.facebook.com/oauth/access_token'
        session = requests.Session()
        response = session.get(url, params={
            'client_id': settings.FACEBOOK_APP_ID,
            'client_secret': settings.FACEBOOK_APP_SECRET,
            'fb_exchange_token': self.access_token,
            'grant_type': 'fb_exchange_token'
        })
        token = json.loads(response.content)

        # Default expire should be within the next hour
        expires_in = arrow.now().replace(hours=1, minute=0)
        if 'expires_in' in token:
            expires_in_days = token['expires_in'] / 60 / 60 / 24  # Value is in seconds
            expires_in = arrow.now().replace(days=expires_in_days, hour=0).datetime

        self.access_token = token.get('access_token')
        self.expires_in = expires_in
        self.save()

        return self.access_token


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
