from django.contrib import admin
from django.utils.translation import gettext_lazy as _

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


class ParentListFilter(admin.SimpleListFilter):
    title = _('Rank')
    parameter_name = 'rank'

    def lookups(self, request, model_admin):
        return (
            ('parent', _('Is Parent')),
            ('child', _('Is Child')),
        )

    def queryset(self, request, queryset):
        if self.value() == 'parent':
            return queryset.filter(
                parent__isnull=True,
            )
        if self.value() == 'child':
            return queryset.filter(
                parent__isnull=False,
            )


@admin.register(AliexpressCategory)
class AliexpressCategoryAdmin(admin.ModelAdmin):
    list_display = (
        'slug',
        'name',
        'aliexpress_id',
        'get_parent_name',
        'created_at',
        'updated_at',
    )
    list_filter = (ParentListFilter, 'created_at', 'updated_at')
    search_fields = ("aliexpress_id", "name", "description")
    raw_id_fields = ('parent',)
    date_hierarchy = 'created_at'

    def get_parent_name(self, obj):
        if obj.parent:
            return obj.parent.name

        return ''
    get_parent_name.short_description = 'Parent'
