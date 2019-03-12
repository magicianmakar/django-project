from django.contrib import admin

from .models import (
    OrderExportVendor,
    OrderExportFilter,
    OrderExport,
    OrderExportQuery,
    OrderExportLog,
    OrderExportFoundProduct,
)


@admin.register(OrderExportFoundProduct)
class OrderExportFoundProductAdmin(admin.ModelAdmin):
    list_display = ('id', 'order_export', 'image_url', 'title', 'product_id')
    raw_id_fields = ('order_export',)


admin.site.register(OrderExportVendor)
admin.site.register(OrderExportFilter)
admin.site.register(OrderExport)
admin.site.register(OrderExportQuery)
admin.site.register(OrderExportLog)
