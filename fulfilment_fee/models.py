from django.contrib.auth.models import User
from django.db import models
import simplejson as json

from lib.exceptions import capture_exception
from shopified_core.models_utils import get_track_model


class SalesFeeConfig(models.Model):
    title = models.CharField(max_length=512, blank=True, default='', verbose_name="Title")
    fee_percent = models.DecimalField(decimal_places=2, max_digits=9, default=0, verbose_name="Sales fee percent")
    fee_flat = models.DecimalField(decimal_places=2, max_digits=9, default=0,
                                   verbose_name="Flat Sales Fee(per item for PLS, but per order for non-PLS)")
    description = models.TextField(blank=True, null=True)

    process_fees_trigger = models.CharField(blank=False, default='always', choices=[('always', 'Always'),
                                                                                    ('count', 'When orders count reached'),
                                                                                    ('amount', 'When orders amount reached')],
                                            verbose_name="When to process fees", max_length=20)
    monthly_free_limit = models.IntegerField(blank=True, default='0',
                                             verbose_name="Apply fees after this count of orders (monthly)")
    monthly_free_amount = models.IntegerField(blank=True, default='0',
                                              verbose_name="Apply fees when this total USD amount reached (monthly)")

    def __str__(self):
        return f'<SalesFeeConfig: {self.id} {self.title} >'

    @property
    def fee_percent_rounded(self):
        integer_percent = int(self.fee_percent)
        if integer_percent == self.fee_percent:
            return integer_percent

        return self.fee_percent


class SaleTransactionFee(models.Model):
    user = models.ForeignKey(User, blank=True, null=True, on_delete=models.CASCADE)
    source_model = models.CharField(max_length=512, blank=True, default='', verbose_name="Which OrderTrack type this fee is related too")
    source_id = models.CharField(max_length=512, blank=True, default='', verbose_name="Source Id")
    fee_value = models.DecimalField(decimal_places=2, max_digits=9, default=0, verbose_name="Sales fee Value")
    processed = models.BooleanField(default=False, verbose_name='Added to invoice or not')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Created date')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Last update')
    currency_conversion_data = models.TextField(null=True, blank=True)

    class Meta:
        unique_together = [['source_model', 'source_id']]

    def get_source(self):
        model = get_track_model(self.source_model)

        try:
            return model.objects.filter(source_id=self.source_id).first()

        except model.DoesNotExist:
            return False

        except:
            capture_exception()
            return False

    @property
    def get_currency_conversion_data(self):
        try:
            return json.loads(self.currency_conversion_data)
        except:
            return False
