import time

from django.db import models

from django.contrib.auth.models import User
from django.utils.functional import cached_property
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

import simplejson as json
import arrow

from .stripe_api import stripe
import stripe.error

from shopified_core import permissions
from leadgalaxy.models import GroupPlan, ShopifyStore
from commercehq_core.models import CommerceHQStore
from woocommerce_core.models import WooStore
from gearbubble_core.models import GearBubbleStore

PLAN_INTERVAL = (
    ('day', 'daily'),
    ('month', 'monthly'),
    ('year', 'yearly'),
    ('week', 'weekly'),
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

    def __unicode__(self):
        return u"Customer: {}".format(self.user.username)

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


class StripePlan(models.Model):
    class Meta:
        verbose_name = "Plan"
        verbose_name_plural = "Plans"

    name = models.CharField(max_length=150)
    plan = models.OneToOneField(GroupPlan, null=True, related_name='stripe_plan', on_delete=models.CASCADE)

    amount = models.DecimalField(decimal_places=2, max_digits=9, verbose_name='Amount(in USD)')
    currency = models.CharField(max_length=15, default='usd')
    retail_amount = models.DecimalField(null=True, decimal_places=2, max_digits=9)

    interval = models.CharField(max_length=15, choices=PLAN_INTERVAL, default='month')
    interval_count = models.IntegerField(default=1)
    trial_period_days = models.IntegerField(default=14)

    statement_descriptor = models.TextField(null=True, blank=True)

    stripe_id = models.CharField(max_length=255, unique=True, editable=False, verbose_name='Stripe Plan ID')
    created_at = models.DateTimeField(auto_now_add=True)

    def __unicode__(self):
        return u"{} (${})".format(self.name, self.amount)

    def save(self, *args, **kwargs):
        from hashlib import md5
        import uuid

        if self.statement_descriptor:
            self.statement_descriptor = self.statement_descriptor.upper().strip()[:22]
        else:
            self.statement_descriptor = None

        if not self.stripe_id:
            self.stripe_id = 'SA_{}'.format(md5(str(uuid.uuid4())).hexdigest()[:8])

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
    plan = models.ForeignKey(GroupPlan, on_delete=models.CASCADE)

    subscription_id = models.CharField(max_length=255, unique=True, editable=False, verbose_name='Stripe Subscription ID')
    status = models.CharField(null=True, blank=True, max_length=64, editable=False, verbose_name='Subscription Status')
    data = models.TextField(null=True, blank=True)

    period_start = models.DateTimeField(null=True)
    period_end = models.DateTimeField(null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __unicode__(self):
        return u"{} {}".format(self.user.username, self.plan.title if self.plan else 'None')

    def retrieve(self, commit=True):
        return stripe.Subscription.retrieve(self.subscription_id)

    def refresh(self, sub=None, commit=True):
        if sub is None:
            sub = stripe.Subscription.retrieve(self.subscription_id)

        self.data = json.dumps(sub)

        self.status = sub.status
        self.period_start = arrow.get(sub.current_period_start).datetime
        self.period_end = arrow.get(sub.current_period_end).datetime

        plan = GroupPlan.objects.filter(stripe_plan__stripe_id=sub.plan.id).first()

        if plan:
            self.user.profile.change_plan(plan)

            if self.plan != plan:
                self.plan = plan

        self.save()

        return sub

    @property
    def subscription(self):
        try:
            return json.loads(self.data)
        except:
            return {}

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
        import arrow

        sub = self.subscription

        status = {
            'status': sub['status'],
            'status_str': sub['status'].replace('_', ' ').title(),
            'cancel_at_period_end': sub['cancel_at_period_end']
        }

        if sub['status'] == 'trialing' and sub.get('trial_end'):
            status['status_str'] = 'Trial ends {}'.format(arrow.get(sub.get('trial_end')).humanize())

        return status


class ExtraStore(models.Model):
    class Meta:
        verbose_name = "Extra Store"
        verbose_name_plural = "Extra Stores"

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    store = models.ForeignKey(ShopifyStore, related_name='extra', on_delete=models.CASCADE)

    status = models.CharField(max_length=64, null=True, blank=True, default='pending')
    period_start = models.DateTimeField(null=True)
    period_end = models.DateTimeField(null=True)
    last_invoice = models.CharField(max_length=64, null=True, blank=True, verbose_name='Last Invoice Item')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    _invoice_name = 'Shopify'

    def __unicode__(self):
        return u"{}".format(self.store.title)


class ExtraCHQStore(models.Model):
    class Meta:
        verbose_name = "Extra CHQ Store"
        verbose_name_plural = "Extra CHQ Stores"

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    store = models.ForeignKey(CommerceHQStore, related_name='extra', on_delete=models.CASCADE)

    status = models.CharField(max_length=64, null=True, blank=True, default='pending')
    period_start = models.DateTimeField(null=True)
    period_end = models.DateTimeField(null=True)
    last_invoice = models.CharField(max_length=64, null=True, blank=True, verbose_name='Last Invoice Item')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    _invoice_name = 'CommerceHQ'

    def __unicode__(self):
        return u"{}".format(self.store.title)


class ExtraWooStore(models.Model):
    class Meta:
        verbose_name = "Extra WooCommerce Store"
        verbose_name_plural = "Extra WooCommerce Stores"

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    store = models.ForeignKey(WooStore, related_name='extra', on_delete=models.CASCADE)

    status = models.CharField(max_length=64, null=True, blank=True, default='pending')
    period_start = models.DateTimeField(null=True)
    period_end = models.DateTimeField(null=True)
    last_invoice = models.CharField(max_length=64, null=True, blank=True, verbose_name='Last Invoice Item')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    _invoice_name = 'WooCommerce'

    def __unicode__(self):
        return u"{}".format(self.store.title)


class ExtraGearStore(models.Model):
    class Meta:
        verbose_name = "Extra GearBubble Store"
        verbose_name_plural = "Extra GearBubble Stores"

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    store = models.ForeignKey(GearBubbleStore, related_name='extra', on_delete=models.CASCADE)

    status = models.CharField(max_length=64, null=True, blank=True, default='pending')
    period_start = models.DateTimeField(null=True)
    period_end = models.DateTimeField(null=True)
    last_invoice = models.CharField(max_length=64, null=True, blank=True, verbose_name='Last Invoice Item')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    _invoice_name = 'GearBubble'

    def __unicode__(self):
        return u"{}".format(self.store.title)


# Signals Handling
def get_extra_model_from_store(store_model):
    if isinstance(store_model, ShopifyStore):
        return ExtraStore
    if isinstance(store_model, CommerceHQStore):
        return ExtraCHQStore
    if isinstance(store_model, WooStore):
        return ExtraWooStore
    if isinstance(store_model, GearBubbleStore):
        return ExtraGearStore


def create_extra_store(sender, instance, created):
    if created:
        try:
            can_add, total_allowed, user_count = permissions.can_add_store(instance.user)
            stores_count = instance.user.profile.get_stores_count()

        except User.DoesNotExist:
            return

        if instance.user.profile.plan.is_stripe() \
                and total_allowed > -1 \
                and total_allowed < stores_count:
            extra_store_model = get_extra_model_from_store(instance)
            extra_store_model.objects.create(
                user=instance.user,
                store=instance,
                period_start=timezone.now())


@receiver(post_save, sender=ShopifyStore)
def add_store_signal(sender, instance, created, **kwargs):
    create_extra_store(sender, instance, created)


@receiver(post_save, sender=CommerceHQStore)
def add_chqstore_signal(sender, instance, created, **kwargs):
    create_extra_store(sender, instance, created)


@receiver(post_save, sender=WooStore)
def add_woostore_signal(sender, instance, created, **kwargs):
    create_extra_store(sender, instance, created)


@receiver(post_save, sender=GearBubbleStore)
def add_gearstore_signal(sender, instance, created, **kwargs):
    create_extra_store(sender, instance, created)
