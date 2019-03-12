from django.contrib import admin

from .models import (
    GearBubbleStore,
    GearBubbleProduct,
    GearBubbleSupplier,
    GearUserUpload,
    GearBubbleBoard,
    GearBubbleOrderTrack
)

USER_SEARCH_FIELDS = ('user__id', 'user__username', 'user__email')


@admin.register(GearBubbleStore)
class GearStoreAdmin(admin.ModelAdmin):
    list_display = ('title', 'user', 'is_active', 'created_at', 'updated_at')
    search_fields = ('title',) + USER_SEARCH_FIELDS
    raw_id_fields = ('user',)
    list_filter = ('is_active',)


@admin.register(GearBubbleProduct)
class GearProductAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'store', 'user', 'created_at', 'updated_at')
    raw_id_fields = ('store', 'user')
    ordering = ('-updated_at',)
    search_fields = ('data', 'source_id')

    def store_(self, obj):
        return obj.store.title


@admin.register(GearBubbleSupplier)
class GearBubbleSupplierAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'store',
        'product',
        'product_url',
        'supplier_name',
        'supplier_url',
        'shipping_method',
        'variants_map',
        'is_default',
        'created_at',
        'updated_at',
    )
    list_filter = ('is_default', 'created_at', 'updated_at')
    raw_id_fields = ('store', 'product')
    date_hierarchy = 'created_at'


@admin.register(GearUserUpload)
class GearUserUploadAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'user',
        'product',
        'url',
        'created_at',
        'updated_at',
    )
    list_filter = ('created_at', 'updated_at')
    raw_id_fields = ('user', 'product')
    date_hierarchy = 'created_at'


@admin.register(GearBubbleBoard)
class GearBubbleBoardAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'user',
        'title',
        'config',
        'favorite',
        'created_at',
        'updated_at',
    )
    list_filter = ('favorite', 'created_at', 'updated_at')
    raw_id_fields = ('user',)
    date_hierarchy = 'created_at'


@admin.register(GearBubbleOrderTrack)
class GearBubbleOrderTrackAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'user',
        'store',
        'order_id',
        'line_id',
        'gearbubble_status',
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
        'created_at',
        'updated_at',
        'status_updated_at',
    )
    list_filter = ('hidden', 'seen', 'auto_fulfilled', 'created_at', 'updated_at', 'status_updated_at')
    raw_id_fields = ('user', 'store')
    date_hierarchy = 'created_at'
