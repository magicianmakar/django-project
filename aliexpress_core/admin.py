from django.contrib import admin

from .models import AliexpressAccount


@admin.register(AliexpressAccount)
class AliexpressAccountAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'user',
        'access_token',
        'aliexpress_user_id',
        'aliexpress_username',
        'data',
        'created_at',
        'updated_at',
    )
    list_filter = ('created_at', 'updated_at')
    raw_id_fields = ('user',)
    date_hierarchy = 'created_at'
