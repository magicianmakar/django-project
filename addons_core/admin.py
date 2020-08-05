from django.contrib import admin

from .models import Addon, AddonUsage


@admin.register(AddonUsage)
class AddonUsageAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'addon',
        'is_active',
        'created_at',
        'updated_at',
        'cancelled_at',
        'billed_at',
    )
    list_filter = ('is_active', 'created_at', 'updated_at', 'cancelled_at')
    date_hierarchy = 'created_at'


@admin.register(Addon)
class AddonAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'title',
        'slug',
        'addon_hash',
        'monthly_price',
        'trial_period_days',
        'hidden',
        'created_at',
        'updated_at',
    )
    prepopulated_fields = {'slug': ('title',)}
    list_filter = ('hidden', 'created_at', 'updated_at')
    search_fields = ('slug',)
    date_hierarchy = 'created_at'
