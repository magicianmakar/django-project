from django.contrib import admin

from .models import (
    OrderExportVendor,
    OrderExportFilter,
    OrderExport,
    OrderExportQuery,
    OrderExportLog,
)


admin.site.register(OrderExportVendor)
admin.site.register(OrderExportFilter)
admin.site.register(OrderExport)
admin.site.register(OrderExportQuery)
admin.site.register(OrderExportLog)
