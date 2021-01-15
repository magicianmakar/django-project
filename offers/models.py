from django.db import models
from django.contrib.auth.models import User
from django.utils.crypto import get_random_string
from django.utils.text import slugify

from addons_core.models import AddonBilling
from leadgalaxy.models import GroupPlan


COUPON_DURATIONS = (
    ('once', 'Once'),
    ('repeating', 'Repeating'),
    ('forever', 'Forever'),
)


class OfferCoupon(models.Model):
    name = models.CharField(
        max_length=255,
        help_text='Name will show in customer invoices'
    )
    percent_off = models.DecimalField(decimal_places=2, max_digits=4)
    duration = models.CharField(max_length=20, choices=COUPON_DURATIONS, default='forever')
    duration_in_months = models.IntegerField(
        null=True,
        blank=True,
        default=None,
        help_text='Required if duration is repeating, specifies the number of months the discount will be in effect'
    )
    redeem_by = models.DateTimeField(
        blank=True,
        null=True,
        help_text='Date after which the coupon can no longer be redeemed.'
    )
    stripe_coupon_id = models.CharField(
        max_length=255,
        blank=True,
        default='',
        help_text='Automatically generated'
    )

    def __str__(self):
        return self.name

    def to_stripe_dict(self):
        stripe_dict = {
            'name': self.name,
            'duration': self.duration,
            'percent_off': float(self.percent_off),
            'metadata': {
                'type': 'offers.OfferCoupon',
                'dropified_id': self.id
            }
        }

        if self.duration == 'repeat':
            stripe_dict['duration_in_months'] = self.duration_in_months

        if self.redeem_by:
            stripe_dict['redeem_by'] = int(self.redeem_by.timestamp())

        return stripe_dict


class Offer(models.Model):
    title = models.CharField(max_length=255, blank=True, default='')
    slug = models.SlugField(max_length=255, blank=True, default='')
    owner = models.ForeignKey(
        User,
        related_name='offers',
        verbose_name='Created by',
        on_delete=models.PROTECT,
        limit_choices_to={'is_staff': True},
    )
    plan = models.ForeignKey(
        GroupPlan,
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name='offers',
        limit_choices_to={
            'payment_gateway': 'stripe',
            'stripe_plan__stripe_id__isnull': False,
            'support_addons': True,
            'payment_interval__in': ['', 'monthly', 'yearly']
        },
    )
    billings = models.ManyToManyField(
        AddonBilling,
        blank=True,
        related_name='offers',
        verbose_name='Addons',
        limit_choices_to={'addon__action_url__isnull': True},
    )
    customers = models.ManyToManyField(
        User,
        through_fields=('offer', 'customer'),
        related_name='purchases',
        through='OfferCustomer'
    )
    coupon = models.ForeignKey(OfferCoupon, blank=True, null=True, on_delete=models.SET_NULL)

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.title:
            self.title = get_random_string(6, 'abcdef0123456789')
            self.slug = slugify(self.title)

        super().save(*args, **kwargs)


class OfferCustomer(models.Model):
    offer = models.ForeignKey(Offer, on_delete=models.CASCADE)
    customer = models.ForeignKey(User, on_delete=models.CASCADE)
    seller = models.ForeignKey(User, related_name='sells', on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Subscribed date')
    amount = models.DecimalField(decimal_places=2, max_digits=9, default=0)
