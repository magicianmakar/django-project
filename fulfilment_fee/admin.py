from django.contrib import admin
from .models import (
    SalesFeeConfig,
    SaleTransactionFee
)


@admin.register(SalesFeeConfig)
class SalesFeeConfigAdmin(admin.ModelAdmin):
    list_display = ('title', 'fee_percent')
    list_filter = ('title', 'fee_percent')


@admin.register(SaleTransactionFee)
class SaleTransactionFeeAdmin(admin.ModelAdmin):
    list_display = ('source_model', 'source_id', 'fee_value')
    list_filter = ('source_model', 'source_id')
