from django.contrib import admin

from .models import (
    GearBubbleStore,
    GearBubbleProduct,
)

USER_SEARCH_FIELDS = ('user__id', 'user__username', 'user__email')


@admin.register(GearBubbleStore)
class GearStoreAdmin(admin.ModelAdmin):
    list_display = ('title', 'user', 'is_active', 'created_at', 'updated_at')
    search_fields = ('title',) + USER_SEARCH_FIELDS
    raw_id_fields = ('user',)
    list_filter = ('is_active',)


@admin.register(GearBubbleProduct)
class GearProductAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'store', 'user', 'created_at', 'updated_at')
    raw_id_fields = ('store', 'user')
    ordering = ('-updated_at',)
    search_fields = ('data', 'source_id')

    def store_(self, obj):
        return obj.store.title
