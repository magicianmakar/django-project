import csv
from django.contrib import admin
from django.http import HttpResponse
from django.utils import timezone

from .models import (
    SalesFeeConfig,
    SaleTransactionFee,
)


class ExportCsvMixin:
    def export_as_csv(self, request, queryset):

        meta = self.model._meta
        field_names = [field.name for field in meta.fields]

        file_name = f'Sale Transaction Fee - {timezone.now()}.csv'
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename={file_name}'
        writer = csv.writer(response)

        writer.writerow(field_names)
        for obj in queryset:
            writer.writerow([getattr(obj, field) for field in field_names])

        return response

    export_as_csv.short_description = "Export Selected"


@admin.register(SalesFeeConfig)
class SalesFeeConfigAdmin(admin.ModelAdmin):
    list_display = ('title', 'fee_percent')
    list_filter = ('title', 'fee_percent')


@admin.register(SaleTransactionFee)
class SaleTransactionFeeAdmin(admin.ModelAdmin):
    list_display = ('source_model', 'source_id', 'fee_value', 'user', 'created_at')
    list_filter = ('source_model',)
    raw_id_fields = ('user',)
    search_fields = ('user__email', 'source_id', 'created_at')
    actions = (ExportCsvMixin.export_as_csv,)
