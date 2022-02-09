import json

import arrow
from django.contrib.auth.models import User
from django.db import models
from django.utils.crypto import get_random_string
from django.utils.functional import cached_property
from django.shortcuts import reverse

from leadgalaxy.models import AppPermission
from shopified_core.utils import app_link, safe_int, safe_str

INTERVAL_CHOICES = ((0, 'Day'), (1, 'Week'), (2, 'Month'), (3, 'Year'))
INTERVAL_ARROW = {0: 'day', 1: 'week', 2: 'month', 3: 'year'}
INTERVAL_STRIPE_MAP = {'day': 0, 'week': 1, 'month': 2, 'year': 3,
                       0: 'day', 1: 'week', 2: 'month', 3: 'year'}


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
        return self.title

    @cached_property
    def visible_addon(self):
        return self.addons.filter(hidden=False)[:3]


class Addon(models.Model):
    variant_from = models.ForeignKey('self', null=True, blank=True, related_name='variants', on_delete=models.SET_NULL)
    categories = models.ManyToManyField(Category, blank=True, related_name="addons")
    permissions = models.ManyToManyField(AppPermission, blank=True)

    title = models.TextField()
    slug = models.SlugField(unique=True, max_length=512)
    store_types = models.CharField(max_length=200, default='', null=True)
    addon_hash = models.TextField(unique=True, editable=False)

    short_description = models.TextField(blank=True)
    description = models.TextField(blank=True)
    churnzero_name = models.TextField(blank=True, default='')
    faq = models.TextField(blank=True, null=True)
    icon_url = models.URLField(blank=True, null=True)
    banner_url = models.URLField(blank=True, null=True)
    youtube_url = models.URLField(blank=True, null=True)
    vimeo_url = models.URLField(blank=True, null=True)
    key_benefits = models.TextField(blank=True, default='')

    action_name = models.CharField(max_length=128, default='Install')
    action_url = models.URLField(blank=True, null=True)
    stores = models.PositiveIntegerField(default=0, verbose_name='Add store limit')
    auto_fulfill_limit = models.PositiveIntegerField(default=0, verbose_name='Add Auto Fulfill Limit')
    hidden = models.BooleanField(default=False, verbose_name='Hidden from users')
    is_active = models.BooleanField(default=True)
    limit_addon = models.BooleanField(default=False, verbose_name="This addon enhances limit & doesn't require permission")

    sales_fees_adjust_free_limit = models.PositiveIntegerField(default=0,
                                                               verbose_name='Increase Fulfilment Fees free Limit (count of orders)')
    sales_fees_adjust_free_amount = models.PositiveIntegerField(default=0,
                                                                verbose_name='Increase Fulfilment Fees free Limit (amount in USD)')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    stripe_product_id = models.CharField(max_length=255, blank=True, default='')

    def __str__(self):
        return self.title

    @property
    def permalink(self):
        return app_link(reverse('addons.details_view',
                                kwargs={'pk': self.id, 'slug': self.slug}))

    @property
    def upsell_anonymous(self):
        return app_link(reverse('addons.upsell_install',
                                kwargs={'pk': self.id, 'slug': self.slug}))

    @property
    def upsell_user(self):
        return app_link(reverse('addons.upsell_install_loggedin',
                                kwargs={'pk': self.id, 'slug': self.slug}))

    def save(self, *args, **kwargs):
        if not self.addon_hash:
            self.addon_hash = get_random_string(32, 'abcdef0123456789')

        if not self.pk:
            self.churnzero_name = self.title

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

    @cached_property
    def store_types_as_list(self):
        return safe_str(self.store_types).split(',')

    def key_benefits_dict(self):
        try:
            return json.loads(self.key_benefits)
        except:
            return []


class IsActiveQuerySet(models.QuerySet):
    def active(self):
        return self.filter(is_active=True)


class AddonBilling(models.Model):
    class Meta:
        ordering = ('sort_order', 'id')

    objects = IsActiveQuerySet.as_manager()

    addon = models.ForeignKey(Addon, related_name='billings', on_delete=models.CASCADE)
    is_active = models.BooleanField(default=True)
    group = models.CharField(max_length=10, default='', blank=True, editable=False)
    sort_order = models.PositiveIntegerField(default=0)

    trial_period_days = models.IntegerField(default=0)
    expire_at = models.DateTimeField(null=True, blank=True)

    interval = models.IntegerField(choices=((None, ''),) + INTERVAL_CHOICES, null=True, default=None)
    interval_count = models.IntegerField(default=1, verbose_name="frequency")

    def __str__(self):
        return self.billing_title

    @cached_property
    def billing_title(self):
        cost = 0
        price = self.prices.first()
        if price:
            cost = price.price
        return f"{self.addon.title} - {self.interval_count}x {self.get_interval_display()} - ${cost}"

    @cached_property
    def max_cost(self):
        return self.prices.order_by('-price').first().price

    def price_for_user(self, user):
        subscription = self.subscriptions.filter(price_after_cancel__isnull=False, user=user).first()

        if subscription is None:
            return self.prices.first()

        return subscription.price_after_cancel


class AddonPrice(models.Model):
    class Meta:
        ordering = ('sort_order', 'id')

    billing = models.ForeignKey(AddonBilling, related_name='prices', on_delete=models.CASCADE)

    price = models.DecimalField(decimal_places=2, max_digits=9)
    price_descriptor = models.CharField(max_length=255, blank=True, default='')
    iterations = models.IntegerField(default=0)  # 0 means infinite
    sort_order = models.PositiveIntegerField(default=0)

    stripe_price_id = models.CharField(max_length=255, blank=True, default='')

    def __str__(self):
        return self.get_price_title()

    def get_price_title(self):
        return self.price_descriptor or self.price_prefix + self.price_sufix

    @property
    def price_prefix(self):
        price_title = f'${self.price}'
        if self.iterations > 0:
            price_title = f'{self.iterations}x {price_title}'

        return price_title

    @cached_property
    def price_sufix(self):
        interval_count = self.billing.interval_count
        if interval_count > 1:
            price_title = f'every {interval_count} {self.billing.get_interval_display()}s'
        else:
            price_title = {0: '/day', 1: '/week', 2: '/mo', 3: '/year'}[self.billing.interval]

        return price_title


class AddonUsage(models.Model):
    class Meta:
        ordering = '-created_at',  # For listing and selecting last one

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    billing = models.ForeignKey(AddonBilling,
                                related_name='subscriptions',
                                on_delete=models.SET_NULL,
                                null=True)

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancel_at = models.DateField(null=True, blank=True)
    price_after_cancel = models.ForeignKey(AddonPrice, null=True, blank=True, on_delete=models.SET_NULL)
    start_at = models.DateField(null=True)
    next_billing = models.DateField(null=True)

    stripe_subscription_id = models.CharField(max_length=255, blank=True, default='')
    stripe_subscription_item_id = models.CharField(max_length=255, blank=True, default='')

    def __str__(self):
        return f'Addon Subscription: {self.id}'

    @cached_property
    def previous_subscriptions(self):
        return self.billing.subscriptions.exclude(id=self.id).filter(
            user=self.user,
            cancelled_at__isnull=False,
        ).annotate(
            usage_delta=models.Sum(models.F('cancelled_at') - models.F('created_at'))
        )

    @cached_property
    def next_price(self):
        if self.cancelled_at:
            return None

        arrow_interval = INTERVAL_ARROW[self.billing.interval]
        iterations = 0
        usage_end_date = self.next_billing or self.cancel_at
        if self.next_billing:
            iterations = len(list(arrow.Arrow.range(
                arrow_interval,
                arrow.get(self.start_at),
                arrow.get(usage_end_date)
            )))

        for subscription in self.previous_subscriptions:
            # Disregard unpaid periods like trials
            if subscription.cancelled_at.date() < subscription.start_at:
                continue

            iterations += len(list(arrow.Arrow.range(
                arrow_interval,
                arrow.get(subscription.start_at).floor('day'),
                arrow.get(subscription.cancelled_at).ceil('day')
            )))

        prices = self.billing.prices.all()
        for price in prices:
            if price.iterations == 0:
                return price

            iterations -= price.iterations
            if iterations <= 0:
                return price

    def get_start_date(self):
        return arrow.get(self.created_at).shift(
            days=self.get_trial_days_left(self.created_at)).date()

    def get_next_billing_date(self, today=None):
        """Get billing date for next cycle, always after today's date
        """
        if self.start_at is None:
            self.start_at = self.get_start_date()
            return self.start_at

        today = today if today else arrow.get().date()
        current_billing_date = self.next_billing or self.start_at
        if current_billing_date > today:
            return current_billing_date

        shift_interval = f"{INTERVAL_ARROW[self.billing.interval]}s"
        shift_date_amount = {shift_interval: self.billing.interval_count}
        next_billing = arrow.get(current_billing_date).shift(**shift_date_amount).date()

        while next_billing <= today:
            next_billing = arrow.get(next_billing).shift(**shift_date_amount).date()

        return next_billing

    def get_trial_days_left(self, from_date=None):
        plan_trial_days = safe_int(self.user.profile.trial_days_left)
        if plan_trial_days == 0 and self.billing.trial_period_days == 0:
            return 0

        trial_usage_days = sum([u.usage_delta.days for u in self.previous_subscriptions])
        trial_usage_days = trial_usage_days if trial_usage_days else 0

        previous_days_left = self.billing.trial_period_days - trial_usage_days
        previous_days_left = previous_days_left if previous_days_left > 0 else 0

        from_date = arrow.get() if not from_date else from_date
        days_left = arrow.get(self.created_at).shift(days=previous_days_left) - from_date

        plan_trial_days += 1  # Plan trial days don't count day one
        addon_trial_days = days_left.days if days_left.days > 0 else 0
        return addon_trial_days if addon_trial_days > plan_trial_days else plan_trial_days
