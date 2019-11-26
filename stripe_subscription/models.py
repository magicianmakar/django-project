import time
import hashlib
import math

from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from django.utils.functional import cached_property
from django.utils.crypto import get_random_string
from raven.contrib.django.raven_compat.models import client as raven_client

import simplejson as json
import arrow
import stripe.error

from shopified_core.utils import safe_json
from .stripe_api import stripe


PLAN_INTERVAL = (
    ('month', 'monthly'),
    ('year', 'yearly'),
)

CUSTOM_PLAN_TYPES = (
    ('callflex_subscription', 'CallFlex Subscription'),
    ('callflex_extranumber', 'CallFlex Extra Number'),
    ('callflex_extraminutes', 'CallFlex Extra Minutes'),

)


class StripeCustomer(models.Model):
    class Meta:
        verbose_name = "Customer"
        verbose_name_plural = "Customers"

    user = models.OneToOneField(User, related_name='stripe_customer', on_delete=models.CASCADE)

    customer_id = models.CharField(max_length=255, null=True, verbose_name='Stripe Customer ID')
    can_trial = models.BooleanField(default=True, verbose_name='Can have trial')
    data = models.TextField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return "Customer: {}".format(self.user.username)

    def stripe_save(self, cus):
        cus = cus.save()
        self.data = json.dumps(cus)
        self.save()

        return cus

    def retrieve(self):
        return stripe.Customer.retrieve(self.customer_id)

    def refresh(self, commit=True):
        cus = stripe.Customer.retrieve(self.customer_id)
        self.data = json.dumps(cus)
        self.save()

        return cus

    def get_data(self):
        return json.loads(self.data)

    def set_data(self, cus):
        self.data = json.dumps(cus)
        self.save()

    def have_source(self):
        cus = self.get_data()
        return cus['sources']['total_count']

    @cached_property
    def source(self):
        cus = self.retrieve()
        return cus.sources.data[0] if cus.sources.total_count else None

    def get_coupon(self, formatted=True):
        cus = self.get_data()
        try:
            coupon = cus['discount']['coupon']
            active = arrow.utcnow() < arrow.get(cus['discount']['end'])
        except:
            coupon = None
            active = False

        if formatted:
            if coupon and active:
                from stripe_subscription.utils import format_coupon
                return format_coupon(coupon)
        else:
            return coupon

    @cached_property
    def invoices(self):
        return self.get_invoices()

    def get_invoices(self):
        invoices = []
        starting_after = None
        while True:
            kwargs = {'limit': 100, 'customer': self.customer_id}
            if starting_after:
                kwargs['starting_after'] = starting_after

            try:
                invoice_list = stripe.Invoice.list(**kwargs)
            except stripe.error.RateLimitError:
                time.sleep(5)
                continue

            invoices += invoice_list.data

            if invoice_list.has_more:
                last_invoice = invoice_list.data.pop()
                starting_after = last_invoice.id
            else:
                break

        return invoices

    def get_charges(self):
        return stripe.Charge.list(limit=10, customer=self.customer_id).data

    @cached_property
    def current_subscription(self):
        subscriptions = self.user.stripesubscription_set.all()

        try:
            plan_stripe_id = self.user.profile.plan.stripe_plan.stripe_id
            for subscription in subscriptions:
                sub_plan = subscription.get_main_subscription_item_plan()
                if sub_plan['id'] == plan_stripe_id:
                    return subscription.subscription
        except:
            raven_client.captureException()
            return False

    @cached_property
    def on_trial(self):
        if self.current_subscription:
            return self.current_subscription['status'] == 'trialing'
        return False

    @cached_property
    def trial_days_left(self):
        if self.current_subscription and self.on_trial:
            trial_end = self.current_subscription['trial_end']
            now = timezone.now()
            delta = arrow.get(trial_end) - arrow.get(now)
            # A 14-day trial would start as 13 days because the moment
            # the trial starts there would be less than 14 days left
            days_left = int(math.floor(delta.total_seconds() / (60 * 60 * 24)))
            return days_left
        return 0


class StripePlan(models.Model):
    class Meta:
        verbose_name = "Plan"
        verbose_name_plural = "Plans"

    name = models.CharField(max_length=150)
    plan = models.OneToOneField('leadgalaxy.GroupPlan', null=True, related_name='stripe_plan', on_delete=models.CASCADE)

    amount = models.DecimalField(decimal_places=2, max_digits=9, verbose_name='Amount(in USD)')
    currency = models.CharField(max_length=15, default='usd')
    retail_amount = models.DecimalField(null=True, decimal_places=2, max_digits=9)

    interval = models.CharField(max_length=15, choices=PLAN_INTERVAL, default='month')
    interval_count = models.IntegerField(default=1)
    trial_period_days = models.IntegerField(default=14)

    statement_descriptor = models.TextField(null=True, blank=True)

    stripe_id = models.CharField(max_length=255, unique=True, editable=False, verbose_name='Stripe Plan ID')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return "{} (${})".format(self.name, self.amount)

    def save(self, *args, **kwargs):
        if self.statement_descriptor:
            self.statement_descriptor = self.statement_descriptor.upper().strip()[:22]
        else:
            self.statement_descriptor = None

        if not self.stripe_id:
            self.stripe_id = 'SA_{}'.format(hashlib.md5(get_random_string(32).encode()).hexdigest()[:8])

            stripe.Plan.create(
                amount=int(self.amount * 100),  # How much to charge in cents, we store it in dollars
                interval=self.interval,
                interval_count=self.interval_count,
                name=self.name,
                currency=self.currency,
                trial_period_days=self.trial_period_days,
                statement_descriptor=self.statement_descriptor,
                id=self.stripe_id
            )
        else:
            p = stripe.Plan.retrieve(self.stripe_id)
            p.name = self.name
            p.statement_descriptor = self.statement_descriptor

            p.save()

        super(StripePlan, self).save(*args, **kwargs)


class StripeSubscription(models.Model):
    class Meta:
        verbose_name = "Subscription"
        verbose_name_plural = "Subscriptions"
        get_latest_by = 'created_at'

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    plan = models.ForeignKey('leadgalaxy.GroupPlan', on_delete=models.CASCADE)

    subscription_id = models.CharField(max_length=255, unique=True, editable=False, verbose_name='Stripe Subscription ID')
    status = models.CharField(null=True, blank=True, max_length=64, editable=False, verbose_name='Subscription Status')
    data = models.TextField(null=True, blank=True)

    period_start = models.DateTimeField(null=True)
    period_end = models.DateTimeField(null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return "{} {}".format(self.user.username, self.plan.title if self.plan else 'None')

    def retrieve(self, commit=True):
        return stripe.Subscription.retrieve(self.subscription_id)

    def refresh(self, sub=None, commit=True):
        from leadgalaxy.models import GroupPlan

        if sub is None:
            sub = stripe.Subscription.retrieve(self.subscription_id)

        self.data = json.dumps(sub)

        self.status = sub.status
        self.period_start = arrow.get(sub.current_period_start).datetime
        self.period_end = arrow.get(sub.current_period_end).datetime

        # getting primary plan from items is multiple plans is set
        # TODO: probably need to replace this by some function/method instead of updating Stripe-native data
        sub_plan = self.get_main_subscription_item_plan(sub=sub)
        plan = GroupPlan.objects.filter(stripe_plan__stripe_id=sub_plan.id).first()

        if plan:
            self.user.profile.change_plan(plan)

            if self.plan != plan:
                self.plan = plan

        self.save()

        return sub

    def get_main_subscription_item_plan(self, sub=None):
        from .utils import get_main_subscription_item

        if sub is None:
            sub = stripe.Subscription.retrieve(self.subscription_id)

        plan_item = get_main_subscription_item(sub=sub)
        if plan_item:
            return plan_item['plan']

    def move_custom_subscriptions(self, sub=None):
        if sub is None:
            sub = stripe.Subscription.retrieve(self.subscription_id)
        custom_subscriptions = self.user.customstripesubscription_set.filter(
            custom_plan__type='callflex_subscription').all()
        if custom_subscriptions.count() > 0:
            items = []
            for custom_subscription in custom_subscriptions:
                items.append({'plan': custom_subscription.custom_plan.stripe_id,
                              'metadata': {'custom_plan_id': custom_subscription.custom_plan.id,
                                           'user_id': self.user.id,
                                           'custom': True,
                                           'custom_plan_type': custom_subscription.custom_plan.type}})
                custom_subscription.safe_delete()

            new_sub = stripe.Subscription.create(
                customer=self.user.stripe_customer.customer_id,
                items=items,
            )

            for si_item in new_sub['items']['data']:
                plan = CustomStripePlan.objects.get(stripe_id=si_item['plan']['id'])
                CustomStripeSubscription.objects.create(
                    user=self.user,
                    custom_plan=plan,
                    data=json.dumps(new_sub),
                    status=new_sub['status'],
                    period_start=arrow.get(new_sub['current_period_start']).datetime,
                    period_end=arrow.get(new_sub['current_period_end']).datetime,
                    subscription_id=new_sub.id,
                    subscription_item_id=si_item.id
                )

    @property
    def subscription(self):
        return safe_json(self.data)

    @property
    def customer_id(self):
        try:
            return self.subscription['customer']
        except:
            return None

    @property
    def is_active(self):
        sub = self.subscription
        return sub['status'] in ['trialing', 'active']

    def get_status(self):
        sub = self.subscription

        status = {
            'status': sub['status'],
            'status_str': sub['status'].replace('_', ' ').title(),
            'cancel_at_period_end': sub['cancel_at_period_end']
        }

        if sub['status'] == 'trialing' and sub.get('trial_end'):
            status['status_str'] = 'Trial ends {}'.format(arrow.get(sub.get('trial_end')).humanize())

        return status

    def can_cancel(self):
        sub = self.retrieve(commit=False)
        return sub['status'] in ['active', 'trialing', 'past_due'] \
            and not sub['cancel_at_period_end'] \
            and not self.plan.is_free


class ExtraStore(models.Model):
    class Meta:
        verbose_name = "Extra Store"
        verbose_name_plural = "Extra Stores"

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    store = models.ForeignKey('leadgalaxy.ShopifyStore', related_name='extra', on_delete=models.CASCADE)

    status = models.CharField(max_length=64, null=True, blank=True, default='pending')
    period_start = models.DateTimeField(null=True)
    period_end = models.DateTimeField(null=True)
    last_invoice = models.CharField(max_length=64, null=True, blank=True, verbose_name='Last Invoice Item')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    _invoice_name = 'Shopify'

    def __str__(self):
        return "{}".format(self.store.title)


class ExtraCHQStore(models.Model):
    class Meta:
        verbose_name = "Extra CHQ Store"
        verbose_name_plural = "Extra CHQ Stores"

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    store = models.ForeignKey('commercehq_core.CommerceHQStore', related_name='extra', on_delete=models.CASCADE)

    status = models.CharField(max_length=64, null=True, blank=True, default='pending')
    period_start = models.DateTimeField(null=True)
    period_end = models.DateTimeField(null=True)
    last_invoice = models.CharField(max_length=64, null=True, blank=True, verbose_name='Last Invoice Item')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    _invoice_name = 'CommerceHQ'

    def __str__(self):
        return "{}".format(self.store.title)


class ExtraWooStore(models.Model):
    class Meta:
        verbose_name = "Extra WooCommerce Store"
        verbose_name_plural = "Extra WooCommerce Stores"

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    store = models.ForeignKey('woocommerce_core.WooStore', related_name='extra', on_delete=models.CASCADE)

    status = models.CharField(max_length=64, null=True, blank=True, default='pending')
    period_start = models.DateTimeField(null=True)
    period_end = models.DateTimeField(null=True)
    last_invoice = models.CharField(max_length=64, null=True, blank=True, verbose_name='Last Invoice Item')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    _invoice_name = 'WooCommerce'

    def __str__(self):
        return "{}".format(self.store.title)


class ExtraGearStore(models.Model):
    class Meta:
        verbose_name = "Extra GearBubble Store"
        verbose_name_plural = "Extra GearBubble Stores"

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    store = models.ForeignKey('gearbubble_core.GearBubbleStore', related_name='extra', on_delete=models.CASCADE)

    status = models.CharField(max_length=64, null=True, blank=True, default='pending')
    period_start = models.DateTimeField(null=True)
    period_end = models.DateTimeField(null=True)
    last_invoice = models.CharField(max_length=64, null=True, blank=True, verbose_name='Last Invoice Item')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    _invoice_name = 'GearBubble'

    def __str__(self):
        return "{}".format(self.store.title)


class CustomStripePlan(models.Model):
    class Meta:
        verbose_name = "Custom Plan"
        verbose_name_plural = "Custom Plans"

    name = models.CharField(max_length=150)
    amount = models.DecimalField(decimal_places=2, max_digits=9, verbose_name='Amount(in USD)')
    currency = models.CharField(max_length=15, default='usd')
    retail_amount = models.DecimalField(null=True, decimal_places=2, max_digits=9)
    interval = models.CharField(max_length=15, choices=PLAN_INTERVAL, default='month')
    interval_count = models.IntegerField(default=1)
    trial_period_days = models.IntegerField(default=14)
    statement_descriptor = models.TextField(null=True, blank=True)
    hidden = models.BooleanField(default=False, verbose_name='Plan is hidden')
    type = models.CharField(max_length=255, choices=CUSTOM_PLAN_TYPES, default='custom')

    # See dropified-webapp/wiki/CallFlex-custom-subscription for details
    credits_data = models.TextField(default='{}', null=True, blank=True, verbose_name='Plan-specific credits set')

    stripe_id = models.CharField(max_length=255, unique=True, editable=False, verbose_name='Stripe Plan ID')
    created_at = models.DateTimeField(auto_now_add=True)

    def __unicode__(self):
        return f"{self.name} (${self.amount})"

    def save(self, *args, **kwargs):
        if self.statement_descriptor:
            self.statement_descriptor = self.statement_descriptor.upper().strip()[:22]
        else:
            self.statement_descriptor = None

        if not self.stripe_id:
            self.stripe_id = 'CP_{}'.format(hashlib.md5(get_random_string(32).encode()).hexdigest()[:8])

            stripe.Plan.create(
                amount=int(self.amount * 100),  # How much to charge in cents, we store it in dollars
                interval=self.interval,
                interval_count=self.interval_count,
                name=self.name,
                currency=self.currency,
                trial_period_days=self.trial_period_days,
                statement_descriptor=self.statement_descriptor,
                id=self.stripe_id,
                metadata={"custom": True, "type": self.type}
            )
        else:
            p = stripe.Plan.retrieve(self.stripe_id)
            p.name = self.name
            p.metadata = {"custom": True, "type": self.type}
            p.statement_descriptor = self.statement_descriptor

            p.save()

        super(CustomStripePlan, self).save(*args, **kwargs)

    @property
    def get_credits_data(self):
        return safe_json(self.credits_data)


class CustomStripeSubscription(models.Model):
    class Meta:
        verbose_name = "Custom Subscription"
        verbose_name_plural = "Custom Subscriptions"
        get_latest_by = 'created_at'

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    custom_plan = models.ForeignKey(CustomStripePlan, null=True)

    subscription_id = models.CharField(max_length=255, editable=False, verbose_name='Stripe Subscription ID')
    subscription_item_id = models.CharField(max_length=255, verbose_name='Stripe Subscription Item ID', null=True)
    status = models.CharField(null=True, blank=True, max_length=64, editable=False, verbose_name='Subscription Status')
    data = models.TextField(null=True, blank=True)

    period_start = models.DateTimeField(null=True)
    period_end = models.DateTimeField(null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __unicode__(self):
        return "{} {}".format(self.user.username, self.custom_plan.name if self.custom_plan else 'None')

    def retrieve(self, commit=True):
        return stripe.Subscription.retrieve(self.subscription_id)

    def refresh(self, sub=None, commit=True):
        if sub is None:
            sub = stripe.Subscription.retrieve(self.subscription_id)

        self.data = json.dumps(sub)

        self.status = sub.status
        self.period_start = arrow.get(sub.current_period_start).datetime
        self.period_end = arrow.get(sub.current_period_end).datetime

        self.save()

        return sub

    @property
    def subscription(self):
        return safe_json(self.data)

    @property
    def customer_id(self):
        try:
            return self.subscription['customer']
        except:
            return None

    @property
    def is_active(self):
        sub = self.subscription
        return sub['status'] in ['trialing', 'active']

    def get_status(self):
        sub = self.subscription

        status = {
            'status': sub['status'],
            'status_str': sub['status'].replace('_', ' ').title(),
            'cancel_at_period_end': sub['cancel_at_period_end']
        }

        if sub['status'] == 'trialing' and sub.get('trial_end'):
            status['status_str'] = 'Trial ends {}'.format(arrow.get(sub.get('trial_end')).humanize())

        return status

    def safe_delete(self, sub=None, commit=True):
        sub = stripe.Subscription.retrieve(self.subscription_id)
        count_items = len(sub['items']['data'])
        if count_items > 1:
            si = stripe.SubscriptionItem.retrieve(self.subscription_item_id)
            si.delete()
        elif count_items == 1 and sub['items']['data'][0].id == self.subscription_item_id:
            sub.delete()
        self.delete()
