from django.db import models
from django.contrib.auth.models import User
from django.urls import reverse
from django.utils.functional import cached_property
from django.utils import timezone

import arrow
import simplejson as json

from lib.exceptions import capture_exception
from shopified_core.utils import send_email_from_template, app_link
from leadgalaxy.models import GroupPlan, ShopifyStore

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
    update_capped_amount_url = models.TextField(null=True, blank=True)

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

        sub_as_dict = sub.to_dict()
        self.data = json.dumps(sub_as_dict)

        self.status = sub.status
        self.update_capped_amount_url = sub_as_dict.get('update_capped_amount_url')
        try:
            self.activated_on = arrow.get(sub.activated_on).to('utc').datetime
        except:
            pass

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


class ShopifySubscriptionWarning(models.Model):
    user = models.OneToOneField(User, related_name='shopify_subscription_warning', on_delete=models.CASCADE)
    shopify_subscription = models.OneToOneField(ShopifySubscription, related_name='warning', on_delete=models.CASCADE)

    subscription_id = models.CharField(max_length=255, unique=True, verbose_name='Charge ID for re-activation')
    confirmation_url = models.TextField(default='')
    created_at = models.DateTimeField(auto_now_add=True)
    expired_at = models.DateField(null=True, blank=True)
    next_warning = models.DateField(null=True, blank=True)

    @property
    def is_expired(self):
        if self.expired_at:
            return arrow.get(self.expired_at) < arrow.get()
        return False

    def send_email(self):
        if self.next_warning and self.next_warning != arrow.get().date():
            return False

        try:
            send_email_from_template(
                tpl='shopify_reactivate_subscription.html',
                subject='Dropified Subscription - action required',
                recipient=self.user.email,
                data={
                    'confirmation_link': app_link(reverse('shopify_subscription.views.shopify_reactivate')),
                }
            )
        except:
            capture_exception()

        current_warning = self.next_warning or self.created_at
        self.next_warning = arrow.get(current_warning).shift(days=5).date()

    def create_charge(self):
        subscription = self.shopify_subscription.subscription
        trial_days = (arrow.get(subscription.get('trial_ends_on')) - arrow.get()).days
        charge = self.shopify_subscription.store.shopify.RecurringApplicationCharge.create({
            "name": subscription['name'],
            "test": subscription['test'],
            "price": subscription['price'],
            "capped_amount": subscription['capped_amount'],
            "return_url": subscription['return_url'],
            "trial_days": trial_days if trial_days > 0 else 0,
            "terms": "Dropified Monthly Subscription",
        })
        sub = ShopifySubscription.objects.create(
            subscription_id=charge.id,
            user=self.user,
            plan=self.shopify_subscription.plan,
            store=self.shopify_subscription.store,
            status=charge.status,
            charge_type=self.shopify_subscription.charge_type,
        )
        sub.refresh(charge)
        self.subscription_id = charge.id
        self.confirmation_url = charge.confirmation_url


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
