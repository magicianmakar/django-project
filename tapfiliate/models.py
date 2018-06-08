from django.db import models


class TapfiliateCommissions(models.Model):
    commission_id = models.CharField(max_length=128, verbose_name='Commission ID')
    conversion_id = models.CharField(max_length=128, verbose_name='Conversion ID')
    affiliate_id = models.CharField(max_length=128, verbose_name='Affiliate ID')
    charge_id = models.CharField(max_length=128, verbose_name='Stripe Charde ID')
    customer_id = models.CharField(max_length=128, verbose_name='Stripe Customer ID')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
