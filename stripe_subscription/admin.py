from django.contrib import admin

# Register your models here.

from .models import (
    StripePlan,
    StripeCustomer,
    StripeSubscription,
    ExtraStore,
    ExtraCHQStore,
    ExtraWooStore,
    ExtraGearStore,
)

from leadgalaxy.models import GroupPlan

USER_SEARCH_FIELDS = ('user__id', 'user__username', 'user__email')


@admin.register(StripePlan)
class StripePlanAdmin(admin.ModelAdmin):
    list_display = ('name', 'plan', 'amount', 'interval', 'stripe_id')
    list_filter = ('interval',)

    def formfield_for_foreignkey(self, db_field, request=None, **kwargs):
        if db_field.name == 'plan':
            kwargs['queryset'] = GroupPlan.objects.filter(payment_gateway='stripe')

        return super(StripePlanAdmin, self).formfield_for_foreignkey(db_field, request, **kwargs)


@admin.register(StripeCustomer)
class StripeCustomerAdmin(admin.ModelAdmin):
    list_display = ('user', 'customer_id', 'created_at', 'updated_at')
    search_fields = ('customer_id',) + USER_SEARCH_FIELDS
    raw_id_fields = ('user',)


@admin.register(StripeSubscription)
class StripeSubscriptionAdmin(admin.ModelAdmin):
    list_display = ('user', 'plan', 'subscription_id', 'created_at', 'updated_at')
    readonly_fields = ('subscription_id',)
    search_fields = ('subscription_id',) + USER_SEARCH_FIELDS
    raw_id_fields = ('user',)


@admin.register(ExtraStore)
class ExtraStoreAdmin(admin.ModelAdmin):
    list_display = ('store', 'user', 'status', 'stores_count', 'is_active', 'last_invoice', 'period_start', 'period_end')
    list_filter = ('status', 'store__is_active')
    search_fields = ('store__title', 'store__id', 'last_invoice') + USER_SEARCH_FIELDS
    raw_id_fields = ('store', 'user')

    def stores_count(self, obj):
        return obj.user.profile.get_shopify_stores().count()

    def is_active(self, obj):
        return obj.store.is_active


@admin.register(ExtraCHQStore)
class ExtraCHQStoreAdmin(admin.ModelAdmin):
    list_display = ('store', 'user', 'status', 'stores_count', 'is_active', 'last_invoice', 'period_start', 'period_end')
    list_filter = ('status', 'store__is_active')
    search_fields = ('store__title', 'store__id', 'last_invoice') + USER_SEARCH_FIELDS
    raw_id_fields = ('store', 'user')

    def stores_count(self, obj):
        return obj.user.profile.get_chq_stores().count()

    def is_active(self, obj):
        return obj.store.is_active


@admin.register(ExtraWooStore)
class ExtraWooStoreAdmin(admin.ModelAdmin):
    list_display = ('store', 'user', 'status', 'stores_count', 'is_active', 'last_invoice', 'period_start', 'period_end')
    list_filter = ('status', 'store__is_active')
    search_fields = ('store__title', 'store__id', 'last_invoice') + USER_SEARCH_FIELDS
    raw_id_fields = ('store', 'user')

    def stores_count(self, obj):
        return obj.user.profile.get_woo_stores().count()

    def is_active(self, obj):
        return obj.store.is_active


@admin.register(ExtraGearStore)
class ExtraGearStoreAdmin(admin.ModelAdmin):
    list_display = ('store', 'user', 'status', 'stores_count', 'is_active', 'last_invoice', 'period_start', 'period_end')
    list_filter = ('status', 'store__is_active')
    search_fields = ('store__title', 'store__id', 'last_invoice') + USER_SEARCH_FIELDS
    raw_id_fields = ('store', 'user')

    def stores_count(self, obj):
        return obj.user.profile.get_gear_stores().count()

    def is_active(self, obj):
        return obj.store.is_active
