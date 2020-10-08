from django.contrib import admin

from .models import (
    StripePlan,
    StripeCustomer,
    StripeSubscription,
    ExtraSubUser,
    ExtraStore,
    ExtraCHQStore,
    ExtraWooStore,
    ExtraGearStore,
    ExtraBigCommerceStore,
    CustomStripePlan,
    CustomStripeSubscription
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


@admin.register(ExtraSubUser)
class ExtraSubUserAdmin(admin.ModelAdmin):
    list_display = ('user', 'status', 'subusers_count', 'last_invoice', 'period_start', 'period_end')
    list_filter = ('status',)
    search_fields = ('last_invoice',) + USER_SEARCH_FIELDS
    raw_id_fields = ('user',)

    def subusers_count(self, obj):
        return obj.user.profile.get_sub_users_count()


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


@admin.register(ExtraBigCommerceStore)
class ExtraBigCommerceStoreAdmin(admin.ModelAdmin):
    list_display = ('store', 'user', 'status', 'stores_count', 'is_active', 'last_invoice', 'period_start', 'period_end')
    list_filter = ('status', 'store__is_active')
    search_fields = ('store__title', 'store__id', 'last_invoice') + USER_SEARCH_FIELDS
    raw_id_fields = ('store', 'user')

    def stores_count(self, obj):
        return obj.user.profile.get_bigcommerce_stores().count()

    def is_active(self, obj):
        return obj.store.is_active


@admin.register(CustomStripePlan)
class CustomStripePlanAdmin(admin.ModelAdmin):
    list_display = ('name', 'type', 'amount', 'interval', 'stripe_id', 'hidden')
    list_filter = ('interval',)


@admin.register(CustomStripeSubscription)
class CustomStripeSubscriptionAdmin(admin.ModelAdmin):
    list_display = ('user', 'custom_plan', 'subscription_id', 'created_at', 'updated_at', 'status')
    readonly_fields = ('subscription_id',)
    search_fields = ('subscription_id',) + USER_SEARCH_FIELDS
    raw_id_fields = ('user',)
