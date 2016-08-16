from django.contrib import admin

# Register your models here.

from .models import (
    StripePlan,
    StripeCustomer,
    StripeSubscription,
    StripeEvent,
    ExtraStore
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
    readonly_fields = ('customer_id',)
    search_fields = ('customer_id',) + USER_SEARCH_FIELDS


@admin.register(StripeSubscription)
class StripeSubscriptionAdmin(admin.ModelAdmin):
    list_display = ('user', 'plan', 'subscription_id', 'created_at', 'updated_at')
    readonly_fields = ('subscription_id',)
    search_fields = ('subscription_id',) + USER_SEARCH_FIELDS


@admin.register(StripeEvent)
class StripeEventAdmin(admin.ModelAdmin):
    list_display = ('event_id', 'event_type', 'created_at')
    readonly_fields = ('event_id', 'created_at')
    list_filter = ('event_type',)
    search_fields = ('event_id', 'event_type')


@admin.register(ExtraStore)
class ExtraStoreAdmin(admin.ModelAdmin):
    list_display = ('store', 'user', 'status', 'last_invoice', 'period_start', 'period_end')
    list_filter = ('status', 'store__is_active')
    search_fields = ('store__title', 'store__id', 'last_invoice') + USER_SEARCH_FIELDS
