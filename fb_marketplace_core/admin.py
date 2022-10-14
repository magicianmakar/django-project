from django.contrib import admin
from django.urls import reverse

from .models import (
    FBMarketplaceBoard,
    FBMarketplaceOrderTrack,
    FBMarketplaceProduct,
    FBMarketplaceStore,
    FBMarketplaceSupplier,
    FBMarketplaceUserUpload
)

USER_SEARCH_FIELDS = ('user__id', 'user__username', 'user__email')


@admin.register(FBMarketplaceStore)
class FBMarketplaceStoreAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'user',
        'title',
        'is_active',
        'created_at',
    )
    list_filter = ('is_active', 'created_at', 'updated_at')
    raw_id_fields = ('user',)
    date_hierarchy = 'created_at'


@admin.register(FBMarketplaceProduct)
class FBMarketplaceProductAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'store', 'user', 'created_at', 'updated_at')
    raw_id_fields = ('user_supplement', 'store', 'user', 'default_supplier', 'parent_product', )
    ordering = ('-updated_at',)
    search_fields = ('data', 'source_id')

    def store_(self, obj):
        return obj.store.title

    def view_on_site(self, obj):
        return reverse('fb_marketplace:product_detail', kwargs={'pk': obj.id})


@admin.register(FBMarketplaceOrderTrack)
class FBMarketplaceOrderTrackAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'store', 'user', 'created_at', 'updated_at')
    raw_id_fields = ('store', 'user')
    ordering = ('-created_at',)
    search_fields = ('data', 'source_id', 'store__id') + USER_SEARCH_FIELDS


@admin.register(FBMarketplaceSupplier)
class FBMarketplaceSupplierAdmin(admin.ModelAdmin):
    list_display = ('id', 'store', 'product', 'supplier_name', 'supplier_url', 'created_at', 'updated_at', )
    list_filter = ('is_default', 'created_at', 'updated_at')
    raw_id_fields = ('store', 'product')
    date_hierarchy = 'created_at'


@admin.register(FBMarketplaceBoard)
class FBMarketplaceBoardAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'title', 'config', 'favorite', 'created_at', 'updated_at')
    list_filter = ('favorite', 'created_at', 'updated_at')
    raw_id_fields = ('user',)
    date_hierarchy = 'created_at'


@admin.register(FBMarketplaceUserUpload)
class FBMarketplaceUserUploadAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'product', 'url', 'created_at', 'updated_at')
    list_filter = ('created_at', 'updated_at')
    raw_id_fields = ('user', 'product')
    date_hierarchy = 'created_at'
