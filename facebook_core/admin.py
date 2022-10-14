# -*- coding: utf-8 -*-
from django.contrib import admin

from .models import FBBoard, FBOrderTrack, FBProduct, FBProductVariant, FBStore, FBSupplier, FBUserUpload

USER_SEARCH_FIELDS = ('user__id', 'user__username', 'user__email')


@admin.register(FBStore)
class FBStoreAdmin(admin.ModelAdmin):
    search_fields = ('title', 'store_hash') + USER_SEARCH_FIELDS
    list_display = (
        'id',
        'list_index',
        'currency_format',
        'sd_account',
        'store_instance_id',
        'user',
        'title',
        'is_active',
        'store_hash',
        'auto_fulfill',
        'created_at',
        'updated_at',
        'store_name',
    )
    list_filter = ('is_active', 'created_at', 'updated_at')
    raw_id_fields = ('sd_account', 'user')
    date_hierarchy = 'created_at'


@admin.register(FBProduct)
class FBProductAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'user',
        'title',
        'price',
        'product_type',
        'tags',
        'boards_list',
        'data',
        'notes',
        'config',
        'variants_map',
        'supplier_map',
        'shipping_map',
        'bundle_map',
        'mapping_config',
        'monitor_id',
        'user_supplement',
        'created_at',
        'updated_at',
        'sd_account',
        'guid',
        'sku',
        'source_id',
        'product_description',
        'condition',
        'thumbnail_image',
        'media_links_data',
        'variants_config',
        'sd_updated_at',
        'store',
        'default_supplier',
        'fb_store_index',
        'fb_category_id',
        'fb_category_name',
        'brand',
        'page_link',
        'status',
    )
    list_filter = ('created_at', 'updated_at', 'sd_updated_at')
    raw_id_fields = (
        'user',
        'user_supplement',
        'sd_account',
        'store',
        'default_supplier',
    )
    date_hierarchy = 'created_at'


@admin.register(FBProductVariant)
class FBProductVariantAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'guid',
        'sku',
        'variant_title',
        'price',
        'image',
        'supplier_sku',
        'source_id',
        'variant_data',
        'created_at',
        'updated_at',
        'parent_product',
        'default_supplier',
        'status',
    )
    list_filter = ('created_at', 'updated_at')
    raw_id_fields = ('parent_product', 'default_supplier')
    date_hierarchy = 'created_at'


@admin.register(FBSupplier)
class FBSupplierAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'product_guid',
        'product_url',
        'supplier_name',
        'supplier_url',
        'shipping_method',
        'variants_map',
        'is_default',
        'created_at',
        'updated_at',
        'store',
        'product',
    )
    list_filter = ('is_default', 'created_at', 'updated_at')
    raw_id_fields = ('store', 'product')
    date_hierarchy = 'created_at'


@admin.register(FBOrderTrack)
class FBOrderTrackAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'user',
        'order_id',
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
        'line_id',
        'fb_status',
    )
    list_filter = (
        'hidden',
        'seen',
        'auto_fulfilled',
        'created_at',
        'updated_at',
        'status_updated_at',
    )
    raw_id_fields = ('user', 'store')
    date_hierarchy = 'created_at'


@admin.register(FBBoard)
class FBBoardAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'title',
        'user',
        'config',
        'favorite',
        'created_at',
        'updated_at',
    )
    list_filter = ('favorite', 'created_at', 'updated_at')
    raw_id_fields = ('user',)
    date_hierarchy = 'created_at'


@admin.register(FBUserUpload)
class FBUserUploadAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'user',
        'url',
        'created_at',
        'updated_at',
        'product',
    )
    list_filter = ('created_at', 'updated_at')
    raw_id_fields = ('user', 'product')
    date_hierarchy = 'created_at'
