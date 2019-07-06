from django.contrib import admin

from .models import ShopifySubscription, BaremetricsCustomer, BaremetricsSubscription, BaremetricsCharge

USER_SEARCH_FIELDS = ('user__id', 'user__username', 'user__email')


@admin.register(ShopifySubscription)
class ShopifySubscriptionAdmin(admin.ModelAdmin):
    list_display = ('user', 'store', 'plan', 'subscription_id', 'status',
                    'data', 'activated_on', 'created_at', 'updated_at', )

    list_filter = ('charge_type', 'status', 'plan__payment_gateway', 'plan__payment_interval')
    raw_id_fields = ('user', 'store')
    readonly_fields = ('subscription_id', 'status', 'activated_on', 'created_at', 'updated_at',)
    search_fields = ('store__id', 'store__title', 'store__shop') + USER_SEARCH_FIELDS


@admin.register(BaremetricsCustomer)
class BaremetricsCustomerAdmin(admin.ModelAdmin):
    list_display = ('id', 'store', 'customer_oid', 'is_active')
    list_filter = ('is_active',)
    raw_id_fields = ('store',)


@admin.register(BaremetricsSubscription)
class BaremetricsSubscriptionAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'customer',
        'shopify_subscription',
        'subscription_oid',
        'status',
        'canceled_at',
    )
    list_filter = ('canceled_at',)
    raw_id_fields = ('customer', 'shopify_subscription')


@admin.register(BaremetricsCharge)
class BaremetricsChargeAdmin(admin.ModelAdmin):
    list_display = ('id', 'customer', 'charge_oid')
    raw_id_fields = ('customer',)
