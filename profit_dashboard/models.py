import arrow
import json
import requests

from django.contrib.auth.models import User
from django.conf import settings
from django.db import models

from facebookads.adobjects.user import User as FBUser

from leadgalaxy.models import ShopifyStore


CONFIG_CHOICES = (
    ('include', 'Include Selected Campaign Only'),
    ('include_and_new', 'Include Selected Campaign and newer ones'),
    ('exclude', 'Exclude Selected Campaign')
)


class FacebookAccess(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    store = models.ForeignKey(ShopifyStore, null=True, on_delete=models.CASCADE)

    access_token = models.CharField(max_length=255)
    expires_in = models.DateTimeField(default=None, null=True, blank=True)
    facebook_user_id = models.CharField(max_length=100, default='')
    account_ids = models.TextField(default='', blank=True)

    def save(self, *args, **kwargs):
        from profit_dashboard.utils import get_facebook_api
        if not self.facebook_user_id:
            api = get_facebook_api(self.access_token)
            user = FBUser(fbid='me', api=api).api_get()
            self.facebook_user_id = user.get('id')

        super(FacebookAccess, self).save(*args, **kwargs)

    def get_or_update_token(self, new_access_token='', new_expires_in=0):
        """
        Exchange current access token for long lived one with +59 days expiration
        """
        # Renew only if old token expires in less than 2 weeks
        if self.expires_in:
            delta_expires_in = self.expires_in - arrow.now().datetime
            if delta_expires_in.days > 7:
                return self.access_token

        # Check if new token is expired
        new_expires_in = arrow.get().replace(seconds=new_expires_in).datetime
        delta_expires_in = new_expires_in - arrow.now().datetime
        if delta_expires_in.seconds < 30:
            raise Exception('Facebook token has expired')

        if new_access_token:
            self.access_token = new_access_token

        # Token exchange must be done manually for now
        url = 'https://graph.facebook.com/oauth/access_token'
        session = requests.Session()
        params = {
            'client_id': settings.FACEBOOK_APP_ID,
            'client_secret': settings.FACEBOOK_APP_SECRET,
            'fb_exchange_token': self.access_token,
            'grant_type': 'fb_exchange_token'
        }
        response = session.get(url, params=params)
        token = json.loads(response.content)

        # Default expire should be within the next hour
        expires_in = arrow.now().replace(hours=1, minute=0).datetime
        if 'expires_in' in token:
            expires_in_days = token['expires_in'] / 60 / 60 / 24  # Value is in seconds
            expires_in = arrow.now().replace(days=expires_in_days, hour=0).datetime
        elif 'error' in token:
            params.update({'response': token})
            raise Exception(params)

        self.access_token = token.get('access_token')
        self.expires_in = expires_in
        self.save()

        return self.access_token


class FacebookAccount(models.Model):
    access = models.ForeignKey(FacebookAccess, related_name='accounts', on_delete=models.CASCADE)
    store = models.ForeignKey(ShopifyStore, null=True, on_delete=models.CASCADE)

    last_sync = models.DateField(null=True)
    account_id = models.CharField(max_length=50)
    account_name = models.CharField(max_length=255)

    config = models.CharField(max_length=100, choices=CONFIG_CHOICES, default='selected')
    campaigns = models.TextField(default='', blank=True)
    updated_at = models.DateTimeField(auto_now=True)


class FacebookAdCost(models.Model):
    account = models.ForeignKey(FacebookAccount,
                                related_name='costs',
                                on_delete=models.CASCADE)
    campaign_id = models.CharField(max_length=100, default='', null=True)
    created_at = models.DateField()
    impressions = models.IntegerField(default=0)
    spend = models.DecimalField(decimal_places=2, max_digits=9)

    class Meta:
        ordering = ['-created_at']


class AliexpressFulfillmentCost(models.Model):
    class Meta:
        ordering = ['-created_at']
        index_together = ['store', 'order_id', 'source_id']

    store = models.ForeignKey(ShopifyStore, on_delete=models.CASCADE)
    order_id = models.BigIntegerField()
    source_id = models.CharField(max_length=512, blank=True, default='')

    created_at = models.DateField(db_index=True)

    shipping_cost = models.DecimalField(decimal_places=2, max_digits=9, default=0)
    products_cost = models.DecimalField(decimal_places=2, max_digits=9, default=0)
    total_cost = models.DecimalField(decimal_places=2, max_digits=9, default=0)


class OtherCost(models.Model):
    store = models.ForeignKey(ShopifyStore, on_delete=models.CASCADE)
    date = models.DateField()
    amount = models.DecimalField(decimal_places=2, max_digits=9, default=0)

    class Meta:
        ordering = ['-date']
