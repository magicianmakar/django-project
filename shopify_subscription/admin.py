from django.contrib import admin

from .models import ShopifySubscription

USER_SEARCH_FIELDS = ('user__id', 'user__username', 'user__email')


@admin.register(ShopifySubscription)
class ShopifySubscriptionAdmin(admin.ModelAdmin):
    list_display = ('user', 'store', 'plan', 'subscription_id', 'status',
                    'data', 'activated_on', 'created_at', 'updated_at', )

    list_filter = ('status',)
    raw_id_fields = ('user', 'store')
    readonly_fields = ('subscription_id', 'status', 'activated_on', 'created_at', 'updated_at',)
    search_fields = ('store__id', 'store__title', 'store__shop') + USER_SEARCH_FIELDS
