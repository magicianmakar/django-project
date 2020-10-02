import json
from decimal import ROUND_HALF_UP, Decimal

from django.contrib.auth.models import User
from django.db import models
from django.utils.crypto import get_random_string
from django.utils.functional import cached_property

import arrow

from leadgalaxy.models import AppPermission


class Category(models.Model):
    class Meta:
        ordering = ['sort_order']
        verbose_name_plural = 'categories'

    title = models.TextField()
    slug = models.SlugField(unique=True, max_length=512)
    short_description = models.TextField(blank=True)
    sort_order = models.PositiveIntegerField(help_text='Sort Order', default=0)
    category_tag = models.TextField(blank=True)

    is_visible = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'Category: {self.title}'


class Addon(models.Model):
    title = models.TextField()
    slug = models.SlugField(unique=True, max_length=512)
    addon_hash = models.TextField(unique=True, editable=False)

    short_description = models.TextField(blank=True)
    description = models.TextField(blank=True)
    faq = models.TextField(blank=True, null=True)

    categories = models.ManyToManyField(Category, blank=True, related_name="addons")

    icon_url = models.URLField(blank=True, null=True)
    banner_url = models.URLField(blank=True, null=True)
    youtube_url = models.URLField(blank=True, null=True)
    vimeo_url = models.URLField(blank=True, null=True)

    monthly_price = models.DecimalField(decimal_places=2, max_digits=9, null=True, blank=True, verbose_name='Monthly Price(in USD)')
    trial_period_days = models.IntegerField(default=0)

    permissions = models.ManyToManyField(AppPermission, blank=True)

    key_benefits = models.TextField(blank=True, default='')

    hidden = models.BooleanField(default=False, verbose_name='Hidden from users')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'Addon: {self.title}'

    def save(self, *args, **kwargs):
        if not self.addon_hash:
            self.addon_hash = get_random_string(32, 'abcdef0123456789')

        super().save(*args, **kwargs)

    def get_key_benefits(self):
        try:
            return json.loads(self.key_benefits)
        except:
            return [
                {'id': 0, 'title': '', 'description': '', 'banner': ''},
                {'id': 1, 'title': '', 'description': '', 'banner': ''},
                {'id': 2, 'title': '', 'description': '', 'banner': ''},
            ]

    def set_key_benefits(self, kb):
        self.key_benefits = json.dumps(kb)


class AddonUsage(models.Model):
    class Meta:
        ordering = '-created_at',

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    addon = models.ForeignKey(Addon, on_delete=models.CASCADE)

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    cancelled_at = models.DateTimeField(null=True, blank=True)
    billed_to = models.DateTimeField(null=True, blank=True)
    billing_day = models.IntegerField(default=1)
    interval_day = models.IntegerField(default=0)

    def __str__(self):
        return f'Addon Subscription: {self.id}'

    @property
    def billing_cycle_ends(self):
        return self.get_next_day(arrow.get(), self.billing_day)

    @cached_property
    def previous_addon_usages(self):
        return self.addon.addonusage_set.exclude(id=self.id).filter(
            user=self.user,
            cancelled_at__isnull=False,
        ).annotate(
            usage_delta=models.Sum(models.F('cancelled_at') - models.F('created_at'))
        )

    def get_trial_days_left(self, today_date=None):
        if self.addon.trial_period_days == 0:
            return 0

        trial_usage_days = sum([u.usage_delta for u in self.previous_addon_usages])
        trial_usage_days = trial_usage_days.days if trial_usage_days else 0

        previous_days_left = self.addon.trial_period_days - trial_usage_days
        previous_days_left = previous_days_left if previous_days_left > 0 else 0

        today_date = arrow.get() if not today_date else today_date
        days_left = arrow.get(self.created_at).shift(days=previous_days_left) - today_date
        return days_left.days if days_left.days > 0 else 0

    def get_next_day(self, d, day):
        from .utils import get_next_day
        return get_next_day(d, day)

    def get_latest_charge(self, today_date=None, save=True):
        """Calculates current charge for addon based on billing period
        """
        today_date = arrow.get() if not today_date else today_date
        today_date = today_date.ceil('day')
        charged_for = Decimal('0.00')

        billing_start = self.billed_to if self.billed_to else self.created_at
        billing_start = arrow.get(billing_start).shift(days=self.get_trial_days_left(billing_start))
        billing_start = self.get_next_day(billing_start, self.interval_day).floor('day')

        # Charge only when today is within billing period
        if billing_start > today_date:
            billing_start = self.billed_to if self.billed_to else self.created_at
            return billing_start, today_date.floor('day'), Decimal('0.00')

        billing_end = self.get_next_day(today_date, self.interval_day).floor('day')
        if billing_end < today_date:  # Today within period
            billing_end = self.get_next_day(
                arrow.get(billing_end).shift(months=1), self.interval_day)

        charged_for += len(list(arrow.Arrow.range('month', billing_start, billing_end.shift(days=-1))))
        # Discount will define a different charge for first month
        if not self.billed_to and not self.previous_addon_usages:
            # charged_for += (self.addon.discounted_price / self.addon.monthly_price) - 1
            pass

        if self.cancelled_at:
            cancelled_at = arrow.get(self.cancelled_at)
            cancelled_period_end = self.get_next_day(cancelled_at, self.interval_day)

            # Cancel can be prorated or ilegible for refund
            last_billing = self.get_next_day(billing_start.shift(months=-1), self.billing_day)
            cancelled_last_period = cancelled_at.is_between(last_billing, billing_start)
            cancelled_at_period = cancelled_at.is_between(billing_start, billing_end)
            if cancelled_last_period or cancelled_at_period:
                cancelled_period_start = cancelled_period_end.shift(months=-1)
                total_days = (cancelled_period_end - cancelled_period_start).days
                left_days = (cancelled_period_end - cancelled_at).days

                # There is a small breach in security for cancelling on the same
                # day as the addon is subscribed
                # At those occurences we'll charge for a single day after 4 hours of usage
                if arrow.get(self.created_at).shift(hours=4) < self.cancelled_at \
                        and self.get_trial_days_left(self.cancelled_at) == 0:
                    left_days -= 1
                charged_for -= Decimal(left_days) / Decimal(total_days)

            # Refunds can happen a few months later, reduce those months from charge
            if cancelled_period_end < billing_end:
                charged_for -= len(list(arrow.Arrow.range('month', billing_start, billing_end.shift(days=-1))))

        self.billed_to = billing_end.floor('day').datetime
        # Refunds will happen manually, save last billing date outside
        if save and charged_for > 0:
            self.save()

        charge_due = (self.addon.monthly_price * charged_for).quantize(Decimal('.01'), ROUND_HALF_UP)
        return billing_start, billing_end, charge_due
