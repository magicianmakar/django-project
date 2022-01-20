from django.contrib import admin

from .models import AliexpressAccount, AliexpressCategory


@admin.register(AliexpressAccount)
class AliexpressAccountAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'user',
        'access_token',
        'aliexpress_user_id',
        'aliexpress_username',
        'created_at',
        'updated_at',
    )
    list_filter = ('created_at', 'updated_at')
    raw_id_fields = ('user',)
    date_hierarchy = 'created_at'


@admin.register(AliexpressCategory)
class AliexpressCategoryAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'name',
        'aliexpress_id',
        'get_parent_name',
        'created_at',
        'updated_at',
    )
    list_filter = ('created_at', 'updated_at')
    raw_id_fields = ('parent',)
    date_hierarchy = 'created_at'

    def get_parent_name(self, obj):
        if obj.parent:
            return obj.parent.name

        return ''
    get_parent_name.short_description = 'Parent'
