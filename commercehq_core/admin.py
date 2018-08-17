from django.contrib import admin
from django.urls import reverse

from .models import (
    CommerceHQStore,
    CommerceHQProduct,
    CommerceHQSupplier,
    CommerceHQBoard,
    CommerceHQOrderTrack,
)

USER_SEARCH_FIELDS = ('user__id', 'user__username', 'user__email')


@admin.register(CommerceHQStore)
class CommerceHQStoreAdmin(admin.ModelAdmin):
    list_display = ('title', 'user', 'is_active', 'auto_fulfill', 'created_at', 'updated_at')
    search_fields = ('title', 'api_url', 'store_hash') + USER_SEARCH_FIELDS
    raw_id_fields = ('user',)
    readonly_fields = ('store_hash',)
    list_filter = ('is_active', 'auto_fulfill')


@admin.register(CommerceHQProduct)
class CommerceHQProductAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'store', 'user', 'created_at', 'updated_at')
    raw_id_fields = ('store', 'user', 'parent_product', 'default_supplier')
    ordering = ('-updated_at',)
    search_fields = ('data', 'notes', 'source_id')

    def store_(self, obj):
        return obj.store.title

    def view_on_site(self, obj):
        return reverse('product_view', kwargs={'pid': obj.id})


@admin.register(CommerceHQSupplier)
class CommerceHQSupplierAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'store', 'supplier_name', 'is_default', 'created_at')
    search_fields = ('product_url', 'supplier_name', 'supplier_url', 'shopify_id')
    raw_id_fields = ('store', 'product')


@admin.register(CommerceHQBoard)
class CommerceHQBoardAdmin(admin.ModelAdmin):
    raw_id_fields = ('user', 'products')


@admin.register(CommerceHQOrderTrack)
class CommerceHQOrderTrackAdmin(admin.ModelAdmin):
    list_display = ('order_id', 'line_id', 'commercehq_status', 'store', 'source_id', 'get_source_status',
                    'status_updated_at', 'seen', 'hidden', 'check_count', 'source_tracking',
                    'created_at', 'updated_at')

    list_filter = ('commercehq_status', 'source_status', 'seen', 'hidden',)
    search_fields = ('order_id', 'line_id', 'source_id', 'source_tracking', 'data')
    raw_id_fields = ('store', 'user')
