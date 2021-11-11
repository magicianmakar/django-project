from django.contrib import admin

from .models import ProductChange


USER_SEARCH_FIELDS = ('user__id', 'user__username', 'user__email')


@admin.register(ProductChange)
class ProductChangeAdmin(admin.ModelAdmin):
    list_display = ('user', 'store_type', 'status', 'created_at', 'updated_at', 'notified_at')
    raw_id_fields = ('user', 'shopify_product', 'chq_product', 'gkart_product', 'woo_product', 'bigcommerce_product')
    search_fields = USER_SEARCH_FIELDS
