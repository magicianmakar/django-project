from django.contrib.auth.models import User
from django.db import models


class SalesFeeConfig(models.Model):
    title = models.CharField(max_length=512, blank=True, default='', verbose_name="Title")
    fee_percent = models.DecimalField(decimal_places=2, max_digits=9, default=0, verbose_name="Sales fee percent")
    description = models.TextField(blank=True, null=True)

    def __str__(self):
        return f'<SalesFeeConfig: {self.id} {self.title} >'


class SaleTransactionFee(models.Model):
    user = models.ForeignKey(User, blank=True, null=True, on_delete=models.CASCADE)
    source_model = models.CharField(max_length=512, blank=True, default='', verbose_name="Which OrderTrack type this fee is related too")
    source_id = models.IntegerField(verbose_name="Source Id")
    fee_value = models.DecimalField(decimal_places=2, max_digits=9, default=0, verbose_name="Sales fee Value")
    processed = models.BooleanField(default=False, verbose_name='Added to invoice or not')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Created date')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Last update')

    class Meta:
        unique_together = [['source_model', 'source_id']]
