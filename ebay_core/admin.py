# -*- coding: utf-8 -*-
from django.contrib import admin

from .models import EbayBoard, EbayOrderTrack, EbayProduct, EbayProductVariant, EbayStore, EbaySupplier, EbayUserUpload

USER_SEARCH_FIELDS = ('user__id', 'user__username', 'user__email')


@admin.register(EbayStore)
class EbayStoreAdmin(admin.ModelAdmin):
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
        'store_username',
        'legacy_auth_token_exp_date',
        'oauth_token_exp_date',
    )
    list_filter = (
        'is_active',
        'created_at',
        'updated_at',
        'legacy_auth_token_exp_date',
        'oauth_token_exp_date',
    )
    raw_id_fields = ('sd_account', 'user')
    date_hierarchy = 'created_at'


@admin.register(EbayProduct)
class EbayProductAdmin(admin.ModelAdmin):
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
        'ebay_store_index',
        'ebay_category_id',
        'ebay_site_id',
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


@admin.register(EbayProductVariant)
class EbayProductVariantAdmin(admin.ModelAdmin):
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
    )
    list_filter = ('created_at', 'updated_at')
    raw_id_fields = ('parent_product', 'default_supplier')
    date_hierarchy = 'created_at'


@admin.register(EbaySupplier)
class EbaySupplierAdmin(admin.ModelAdmin):
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


@admin.register(EbayOrderTrack)
class EbayOrderTrackAdmin(admin.ModelAdmin):
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
        'ebay_status',
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


@admin.register(EbayBoard)
class EbayBoardAdmin(admin.ModelAdmin):
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


@admin.register(EbayUserUpload)
class EbayUserUploadAdmin(admin.ModelAdmin):
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
