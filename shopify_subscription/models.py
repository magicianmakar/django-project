from django.db import models
from django.contrib.auth.models import User
from django.utils.functional import cached_property
from django.utils import timezone

import arrow
import simplejson as json

from leadgalaxy.models import GroupPlan, ShopifyStore
from shopified_core.utils import safe_json

SHOPIFY_CHARGE_TYPE = (
    ('recurring', 'Recurring'),
    ('single', 'Single Charge'),
)


class ShopifySubscription(models.Model):
    class Meta:
        verbose_name = "Subscription"
        verbose_name_plural = "Subscriptions"
        get_latest_by = 'created_at'

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    store = models.ForeignKey(ShopifyStore, on_delete=models.CASCADE)
    plan = models.ForeignKey(GroupPlan, null=True, on_delete=models.CASCADE)

    charge_type = models.CharField(max_length=25, choices=SHOPIFY_CHARGE_TYPE, default='recurring')

    subscription_id = models.CharField(max_length=255, unique=True, verbose_name='Shopify Charge ID')
    status = models.CharField(null=True, blank=True, max_length=64, verbose_name='Shopify Charge Status')
    data = models.TextField(null=True, blank=True)

    activated_on = models.DateTimeField(null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return "{} {}".format(self.user.username, self.plan.title if self.plan else 'None')

    def retrieve(self, commit=True):
        if self.charge_type == 'recurring':
            return self.store.shopify.RecurringApplicationCharge.find(self.subscription_id)
        else:
            return self.store.shopify.ApplicationCharge.find(self.subscription_id)

    def refresh(self, sub=None, commit=True):
        if sub is None:
            sub = self.retrieve()

        self.data = json.dumps(sub.to_dict())

        self.status = sub.status
        try:
            self.activated_on = arrow.get(sub.activated_on).to('utc').datetime
        except:
            pass

        self.save()

        return sub

    @property
    def subscription(self):
        return safe_json(self.data)

    @property
    def is_active(self):
        sub = self.subscription
        return sub['status'] in ['accepted', 'active']

    @cached_property
    def on_trial(self):
        if self.trial_days_left is not None:
            return not self.trial_days_left < 0
        return False

    @cached_property
    def trial_days_left(self):
        self.refresh()
        # Note: The `trial_ends_on` date is not a datetime value so it's
        # impossible to know when exactly the trial ends on that day
        trial_ends_on = self.subscription.get('trial_ends_on')
        if trial_ends_on:
            delta = arrow.get(trial_ends_on).date() - timezone.now().date()
            return delta.days

    def get_status(self):
        sub = self.subscription

        status = {
            'status': sub['status'],
            'status_str': sub['status'].title(),
        }

        if sub['status'] == 'trialing' and sub.get('trial_end'):
            status['status_str'] = 'Trial ends {}'.format(arrow.get(sub.get('trial_end')).humanize())

        return status


class BaremetricsCustomer(models.Model):
    store = models.OneToOneField(ShopifyStore, related_name='baremetrics_customer', null=True, on_delete=models.CASCADE)
    customer_oid = models.CharField(max_length=50)
    is_active = models.BooleanField(default=True)


class BaremetricsSubscription(models.Model):
    customer = models.ForeignKey(BaremetricsCustomer, related_name='subscriptions', on_delete=models.CASCADE)
    shopify_subscription = models.OneToOneField(ShopifySubscription, related_name='baremetrics_subscription', on_delete=models.CASCADE)
    subscription_oid = models.CharField(max_length=50)
    status = models.CharField(null=True, blank=True, max_length=64, verbose_name='Shopify Charge Status')
    canceled_at = models.DateTimeField(null=True)


class BaremetricsCharge(models.Model):
    customer = models.ForeignKey(BaremetricsCustomer, related_name='charges', on_delete=models.CASCADE)
    charge_oid = models.CharField(max_length=50)
