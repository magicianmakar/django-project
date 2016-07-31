from django.contrib import admin

from .models import ProductRevision


@admin.register(ProductRevision)
class ProductRevisionAdmin(admin.ModelAdmin):
    list_display = ('product', 'store', 'shopify_id', 'created_at')
    raw_id_fields = ('store', 'product', 'product_change')
    search_fields = ('store__id', 'store__title', 'product__id', 'product__title', 'shopify_id')
    exclude = []
