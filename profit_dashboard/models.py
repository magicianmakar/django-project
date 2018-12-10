import arrow
import json
import requests
from collections import defaultdict
from datetime import date
from time import sleep

from django.contrib.auth.models import User
from django.conf import settings
from django.db import models

from raven.contrib.django.raven_compat.models import client as raven_client

from facebookads.api import FacebookAdsApi
from facebookads.adobjects.user import User as FBUser
from facebookads.adobjects.adaccount import AdAccount
from facebookads.adobjects.adreportrun import AdReportRun
from facebookads.exceptions import FacebookRequestError

from leadgalaxy.models import ShopifyStore


CONFIG_CHOICES = (
    ('include', 'Include Selected Campaign Only'),
    ('include_and_new', 'Include Selected Campaign and newer ones'),
    ('exclude', 'Exclude Selected Campaign')
)

FACEBOOK_INSIGHTS_TIMEOUT = 120
INITIAL_DATE = arrow.get('2018-06-01')


class FacebookAccess(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    store = models.ForeignKey(ShopifyStore, null=True, on_delete=models.CASCADE)

    access_token = models.CharField(max_length=255)
    expires_in = models.DateTimeField(default=None, null=True, blank=True)
    facebook_user_id = models.CharField(max_length=100, default='')
    account_ids = models.TextField(default='', blank=True)

    def save(self, *args, **kwargs):
        try:
            self._reload_api()
            if not self.facebook_user_id:
                user = FBUser(fbid='me', api=self.api).api_get()
                self.facebook_user_id = user.get('id')

        except FacebookRequestError, e:
            if e.api_error_code() == 190:  # (#190) Error validating access token
                self.access_token = ''
                self.expires_in = None

                raven_client.captureException(level='warning')
            else:
                raven_client.captureException()

        except:
            raven_client.captureException()

        super(FacebookAccess, self).save(*args, **kwargs)

    def _reload_api(self):
        access_token = self.get_or_update_token()
        self._api = FacebookAdsApi.init(
            settings.FACEBOOK_APP_ID,
            settings.FACEBOOK_APP_SECRET,
            access_token,
            api_version='v3.0'
        )

    @property
    def api(self):
        if not hasattr(self, '_api'):
            self._reload_api()
        return self._api

    def get_or_update_token(self, new_access_token='', new_expires_in=0):
        """
        Exchange current access token for long lived one with +59 days expiration
        """
        # Renew only if old token expires in less than one week
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

    def get_api_accounts(self):
        user = FBUser(fbid='me', api=self.api)
        return user.get_ad_accounts(fields=[AdAccount.Field.name])


class FacebookAccount(models.Model):
    access = models.ForeignKey(FacebookAccess, related_name='accounts', on_delete=models.CASCADE)
    store = models.ForeignKey(ShopifyStore, null=True, on_delete=models.CASCADE)

    last_sync = models.DateField(null=True)
    account_id = models.CharField(max_length=50)
    account_name = models.CharField(max_length=255)

    config = models.CharField(max_length=100, choices=CONFIG_CHOICES, default='selected')
    campaigns = models.TextField(default='', blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def _get_last_sync_params(self):
        return {
            'since': arrow.get(self.last_sync).replace(days=-1).format('YYYY-MM-DD'),
            'until': date.today().strftime('%Y-%m-%d')
        }

    @property
    def ad_account(self):
        return AdAccount(self.account_id, api=self.access.api)

    @property
    def is_first_sync(self):
        if self.last_sync:
            return self.last_sync == INITIAL_DATE.date()

        return False

    def get_api_campaigns(self, after_last_sync=False):
        params = {'limit': 1000}

        if after_last_sync and self.last_sync:
            params['created_time'] = self._get_last_sync_params()

        return self.ad_account.get_campaigns(fields=['name', 'status', 'created_time'], params=params)

    def get_api_campaigns_selected(self):
        campaign_ids = []
        if 'include' in self.config:
            campaign_ids = [c for c in self.campaigns.split(',') if c]

            if 'new' in self.config:
                new_campaigns_found = False
                for campaign in self.get_api_campaigns(after_last_sync=True):
                    campaign_date = arrow.get(campaign['created_time']).datetime
                    if campaign['id'] and campaign_date > self.updated_at:
                        new_campaigns_found = True
                        campaign_ids.append(campaign['id'])

                # Save only if new campaigns are found
                if new_campaigns_found:
                    self.campaigns = ','.join(campaign_ids)
                    self.save()

        elif 'exclude' in self.config:
            for campaign in self.get_api_campaigns():
                if campaign['id'] and campaign['id'] not in self.campaigns:
                    campaign_ids.append(campaign['id'])

        return campaign_ids

    def get_api_insights(self, verbosity):
        params = {
            'time_increment': 1,
            'level': 'campaign',
            'limit': 500,
            'filtering': [{
                'field': 'campaign.id',
                'operator': 'IN',
                'value': self.get_api_campaigns_selected()
            }]
        }

        if self.last_sync:
            params['time_range'] = self._get_last_sync_params()

        # AdAccount.get_insights method iterates with endpoint pagination and loads all insights before returning
        insights_async_job = self.ad_account.get_insights_async(params=params)

        seconds = 0

        # Takes ~100 seconds to prepare ~4000 insights
        while FACEBOOK_INSIGHTS_TIMEOUT < seconds or self.is_first_sync:
            seconds += 1
            job = insights_async_job.remote_read()
            sleep(1)
            if job and job[AdReportRun.Field.async_percent_completion] == 100 and \
                    job[AdReportRun.Field.async_status] != 'Job Running':
                break

        campaign_insights = {}
        campaign_insights_length = defaultdict(int)

        # Get insights 500 at a time
        insights = job.get_result(params={'limit': 500})
        # :insights facebookads.api.Cursor: Iterates over all insights, not only 500
        for insight in insights:
            campaign_id = insight[insight.Field.campaign_id]
            if verbosity > 2:
                campaign_insights_length[campaign_id] += 1

            insight_date = arrow.get(insight[insight.Field.date_start]).format('YYYY-MM-DD')
            insight_key = '{}-{}'.format(insight_date, campaign_id)
            if insight_key not in campaign_insights:
                campaign_insights[insight_key] = {
                    'impressions': int(insight[insight.Field.impressions]),
                    'spend': float(insight[insight.Field.spend]),
                    'created_at': arrow.get(insight[insight.Field.date_start]).date(),
                    'campaign_id': campaign_id,
                }
            else:
                campaign_insights[insight_key]['impressions'] += int(insight[insight.Field.impressions])
                campaign_insights[insight_key]['spend'] += float(insight[insight.Field.spend])

        if verbosity > 2:
            for campaign_id, insights_length in campaign_insights_length.items():
                print '\t\tCampaigns {} have {} Insights'.format(campaign_id, insights_length)

        return campaign_insights.values()


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

    def get_insights(self):
        pass


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
