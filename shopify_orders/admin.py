from django.contrib import admin

from shopify_orders.models import (
    ShopifyFulfillementRequest,
    ShopifyOrder,
    ShopifyOrderLine,
    ShopifyOrderLog,
    ShopifyOrderRevenue,
    ShopifyOrderRisk,
    ShopifyOrderShippingLine,
    ShopifyOrderVariant,
    ShopifySyncStatus,
)

USER_SEARCH_FIELDS = ('user__id', 'user__username', 'user__email')


@admin.register(ShopifySyncStatus)
class ShopifySyncStatusAdmin(admin.ModelAdmin):
    list_display = ('store', 'sync_type', 'sync_status', 'elastic', 'orders_count', 'created_at', 'updated_at')
    list_filter = ('sync_type', 'sync_status', 'elastic')
    raw_id_fields = ('store',)
    search_fields = ['store__id', 'store__shop'] + ['store__' + i for i in USER_SEARCH_FIELDS]


@admin.register(ShopifyOrder)
class ShopifyOrderApiAdmin(admin.ModelAdmin):
    list_display = ('order_id', 'financial_status', 'fulfillment_status', 'created_at', 'updated_at', 'closed_at')
    raw_id_fields = ('user', 'store')
    search_fields = ('store__id', 'store__shop') + USER_SEARCH_FIELDS


@admin.register(ShopifyOrderLine)
class ShopifyOrderLineAdmin(admin.ModelAdmin):
    list_display = ('line_id', 'order', 'track', 'variant_title')
    raw_id_fields = ('product', 'order', 'track')


@admin.register(ShopifyOrderRisk)
class ShopifyOrderRiskeAdmin(admin.ModelAdmin):
    list_display = ('store', 'order_id', 'created_at')
    raw_id_fields = ('store',)
    search_fields = ('store__id', 'store__shop')


@admin.register(ShopifyOrderLog)
class ShopifyOrderLogAdmin(admin.ModelAdmin):
    list_display = ('store', 'order_id', 'seen', 'created_at', 'updated_at')
    raw_id_fields = ('store',)
    search_fields = ('store__id', 'store__shop', 'order_id')


@admin.register(ShopifyOrderShippingLine)
class ShopifyOrderShippingLineAdmin(admin.ModelAdmin):
    list_display = ('id', 'store', 'order', 'shipping_line_id', 'price', 'title', 'code', 'source', 'phone', 'carrier_identifier', )
    raw_id_fields = ('store', 'order')


@admin.register(ShopifyOrderVariant)
class ShopifyOrderVariantAdmin(admin.ModelAdmin):
    list_display = ('id', 'store', 'changed_by', 'order_id', 'line_id', 'variant_id', 'variant_title', 'created_at', 'updated_at')
    list_filter = ('created_at', 'updated_at')
    raw_id_fields = ('store', 'changed_by')
    date_hierarchy = 'created_at'


@admin.register(ShopifyOrderRevenue)
class ShopifyOrderRevenueAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'user',
        'store',
        'order_id',
        'currency',
        'items_count',
        'line_items_price',
        'shipping_price',
        'total_price',
        'total_price_usd',
        'created_at',
    )
    list_filter = ('created_at',)
    raw_id_fields = ('user', 'store')
    date_hierarchy = 'created_at'


@admin.register(ShopifyFulfillementRequest)
class ShopifyFulfillementRequestAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'store',
        'fulfillment_order_id',
        'status',
        'order_id',
        'assigned_location_id',
        'created_at',
        'updated_at',
    )
    list_filter = ('created_at', 'updated_at')
    raw_id_fields = ('store',)
    date_hierarchy = 'created_at'
