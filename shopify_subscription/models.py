from django.db import models
from django.contrib.auth.models import User

import arrow
import simplejson as json

from leadgalaxy.models import GroupPlan, ShopifyStore


class ShopifySubscription(models.Model):
    class Meta:
        verbose_name = "Subscription"
        verbose_name_plural = "Subscriptions"
        get_latest_by = 'created_at'

    user = models.ForeignKey(User)
    store = models.ForeignKey(ShopifyStore)
    plan = models.ForeignKey(GroupPlan, null=True)

    subscription_id = models.CharField(max_length=255, unique=True, verbose_name='Shopify Charge ID')
    status = models.CharField(null=True, blank=True, max_length=64, verbose_name='Shopify Charge Status')
    data = models.TextField(null=True, blank=True)

    activated_on = models.DateTimeField(null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __unicode__(self):
        return u"{} {}".format(self.user.username, self.plan.title)

    def retrieve(self, commit=True):
        return self.store.shopify.RecurringApplicationCharge.find(self.subscription_id)

    def refresh(self, sub=None, commit=True):
        if sub is None:
            sub = self.retrieve()

        self.data = json.dumps(sub.to_dict())

        self.status = sub.status
        self.activated_on = sub.activated_on

        self.save()

        return sub

    @property
    def subscription(self):
        try:
            return json.loads(self.data)
        except:
            return {}

    @property
    def is_active(self):
        sub = self.subscription
        return sub['status'] in ['accepted', 'active']

    def get_status(self):
        sub = self.subscription

        status = {
            'status': sub['status'],
            'status_str': sub['status'].title(),
        }

        if sub['status'] == 'trialing' and sub.get('trial_end'):
            status['status_str'] = 'Trial ends {}'.format(arrow.get(sub.get('trial_end')).humanize())

        return status
