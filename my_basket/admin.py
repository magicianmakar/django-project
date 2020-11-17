from django.contrib import admin

from .models import BasketOrderTrack


@admin.register(BasketOrderTrack)
class BasketOrderTrackAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'user',
        'order_id',
        'line_id',
        'source_id',
        'source_status',
        'source_tracking',
        'source_status_details',
        'source_type',
        'hidden',
        'seen',
        'auto_fulfilled',
        'check_count',
        'data',
        'errors',
        'created_at',
        'updated_at',
        'status_updated_at',
        'store',
        'product_id',
        'basket_order_status',
    )
    list_filter = (
        'hidden',
        'seen',
        'auto_fulfilled',
        'created_at',
        'updated_at',
        'status_updated_at',
    )
    raw_id_fields = ('user',)
    date_hierarchy = 'created_at'
