from django.contrib import admin

from .models import (
    GrooveKartStore,
    GrooveKartProduct,
    GrooveKartSupplier,
    GrooveKartUserUpload,
    GrooveKartBoard,
    GrooveKartOrderTrack,
)


USER_SEARCH_FIELDS = ('user__id', 'user__username', 'user__email')


@admin.register(GrooveKartStore)
class GrooveKartStoreAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'user',
        'title',
        'api_url',
        'api_key',
        'api_token',
        'is_active',
        'store_hash',
        'created_at',
        'updated_at',
    )
    list_filter = ('is_active', 'created_at', 'updated_at')
    raw_id_fields = ('user',)
    date_hierarchy = 'created_at'
    search_fields = ('title', 'api_url', 'store_hash') + USER_SEARCH_FIELDS


@admin.register(GrooveKartProduct)
class GrooveKartProductAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'store',
        'user',
        'data',
        'notes',
        'title',
        'price',
        'tags',
        'product_type',
        'source_id',
        'source_slug',
        'default_supplier',
        'variants_map',
        'supplier_map',
        'shipping_map',
        'mapping_config',
        'parent_product',
        'created_at',
        'updated_at',
    )
    list_filter = ('created_at', 'updated_at')
    raw_id_fields = ('store', 'user', 'default_supplier', 'parent_product')
    date_hierarchy = 'created_at'
    search_fields = USER_SEARCH_FIELDS


@admin.register(GrooveKartSupplier)
class GrooveKartSupplierAdmin(admin.ModelAdmin):
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


@admin.register(GrooveKartUserUpload)
class GrooveKartUserUploadAdmin(admin.ModelAdmin):
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


@admin.register(GrooveKartBoard)
class GrooveKartBoardAdmin(admin.ModelAdmin):
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


@admin.register(GrooveKartOrderTrack)
class GrooveKartOrderTrackAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'user',
        'store',
        'order_id',
        'line_id',
        'groovekart_status',
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
