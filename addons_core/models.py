import json
from decimal import Decimal, ROUND_HALF_UP

import arrow
from django.contrib.auth.models import User
from django.db import models
from django.utils.crypto import get_random_string

from leadgalaxy.models import AppPermission


class Category(models.Model):
    class Meta:
        ordering = ['sort_order']
        verbose_name_plural = 'categories'

    title = models.TextField()
    slug = models.SlugField(unique=True, max_length=512)
    short_description = models.TextField()
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

    short_description = models.TextField()
    description = models.TextField()

    categories = models.ManyToManyField(Category, blank=True, related_name="addons")

    icon_url = models.TextField(blank=True, null=True)
    banner_url = models.TextField(blank=True, null=True)
    youtube_url = models.TextField(blank=True, null=True)

    monthly_price = models.DecimalField(decimal_places=2, max_digits=9, null=True, blank=True, verbose_name='Monthly Price(in USD)')
    trial_period_days = models.IntegerField(default=0)

    permissions = models.ManyToManyField(AppPermission, blank=True)

    key_benfits = models.TextField(blank=True, default='')

    hidden = models.BooleanField(default=False, verbose_name='Hidden from users')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'Addon: {self.title}'

    def save(self, *args, **kwargs):
        if not self.addon_hash:
            self.addon_hash = get_random_string(32, 'abcdef0123456789')

        super().save(*args, **kwargs)

    def get_key_benfits(self):
        try:
            return json.loads(self.key_benfits)
        except:
            return [
                {'id': 0, 'title': '', 'description': '', 'banner': ''},
                {'id': 1, 'title': '', 'description': '', 'banner': ''},
                {'id': 2, 'title': '', 'description': '', 'banner': ''},
            ]

    def set_key_benfits(self, kb):
        self.key_benfits = json.dumps(kb)


class AddonUsage(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    addon = models.ForeignKey(Addon, on_delete=models.CASCADE)

    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    billed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f'Addon Subscription: {self.id}'

    def usage_charge(self, last_billed_at=None):
        today = arrow.get()
        if self.cancelled_at is not None:
            today = arrow.get(self.cancelled_at)

        if self.billed_at is not None:
            billing_day = arrow.get(self.billed_at)
        else:
            billing_day = arrow.get(self.created_at)

        # shift trial period
        if self.addon.trial_period_days > 0:
            first_install = self.addon.addonusage_set.filter(user=self.user).order_by('created_at').first()
            billing_day = billing_day.shift(days=first_install.addon.trial_period_days)

        if last_billed_at is not None:
            last_billed_at = arrow.get(last_billed_at)
            if last_billed_at > billing_day:
                billing_day = last_billed_at

        total_days = 0
        total_percentage = 0
        for month in arrow.Arrow.range('month', billing_day, today.replace(days=-1)):
            total_days += month.ceil('month').day
            total_percentage += 100

        usage_days = today - billing_day

        if total_days > 0:
            percentage = Decimal(usage_days.days) * total_percentage / total_days
        else:
            percentage = 0
        charge = Decimal(self.addon.monthly_price) * percentage / 100
        return charge.quantize(Decimal('.01'), ROUND_HALF_UP)
