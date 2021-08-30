from django.contrib import admin

from .models import ProductBoard


@admin.register(ProductBoard)
class ProductBoardAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'title',
        'user',
        'config',
        'favorite',
        'created_at',
        'updated_at',
    )
    list_filter = ('favorite', 'created_at', 'updated_at')
    raw_id_fields = ('user',)
    date_hierarchy = 'created_at'
