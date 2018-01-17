from django.contrib import admin

# Register your models here.

from shopify_orders.models import ShopifySyncStatus, ShopifyOrder, ShopifyOrderLine, ShopifyOrderRisk


@admin.register(ShopifySyncStatus)
class ShopifySyncStatusAdmin(admin.ModelAdmin):
    list_display = ('store', 'sync_type', 'sync_status', 'orders_count', 'created_at', 'updated_at')
    list_filter = ('sync_type', 'sync_status')
    raw_id_fields = ('store',)


@admin.register(ShopifyOrder)
class ShopifyOrderApiAdmin(admin.ModelAdmin):
    list_display = ('order_id', 'financial_status', 'fulfillment_status', 'created_at', 'updated_at', 'closed_at')
    raw_id_fields = ('user', 'store')


@admin.register(ShopifyOrderLine)
class ShopifyOrderLineAdmin(admin.ModelAdmin):
    list_display = ('line_id', 'order', 'track', 'variant_title')
    raw_id_fields = ('product', 'order', 'track')

@admin.register(ShopifyOrderRisk)
class ShopifyOrderRiskeAdmin(admin.ModelAdmin):
    list_display = ('store', 'order_id', 'created_at')
    raw_id_fields = ('store',)
