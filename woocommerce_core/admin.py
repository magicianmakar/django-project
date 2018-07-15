from django.contrib import admin
from django.core.urlresolvers import reverse

from .models import (
    WooStore,
    WooProduct,
    WooSupplier,
    WooOrderTrack,
    WooBoard,
)

USER_SEARCH_FIELDS = ('user__id', 'user__username', 'user__email')


@admin.register(WooStore)
class WooStoreAdmin(admin.ModelAdmin):
    list_display = ('title', 'user', 'is_active', 'created_at', 'updated_at')
    search_fields = ('title', 'api_url') + USER_SEARCH_FIELDS
    raw_id_fields = ('user',)
    list_filter = ('is_active',)


@admin.register(WooProduct)
class WooProductAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'store', 'user', 'created_at', 'updated_at')
    raw_id_fields = ('store', 'user')
    ordering = ('-updated_at',)
    search_fields = ('data', 'source_id')

    def store_(self, obj):
        return obj.store.title

    def view_on_site(self, obj):
        return reverse('product_view', kwargs={'pid': obj.id})


@admin.register(WooOrderTrack)
class WooOrderTrackAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'store', 'user', 'created_at', 'updated_at')
    raw_id_fields = ('store', 'user')
    ordering = ('-created_at',)
    search_fields = ('data', 'source_id', 'store__id') + USER_SEARCH_FIELDS


admin.site.register(WooSupplier)
admin.site.register(WooBoard)
