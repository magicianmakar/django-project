from django.contrib import admin
from .models import (
    FacebookAccess,
    FacebookAccount,
    FacebookAdCost,
    FulfillmentCost,
    OtherCost,
    ProfitSync,
    ProfitOrder,
    ProfitRefund,
)


@admin.register(FacebookAccess)
class FacebookAccessAdmin(admin.ModelAdmin):
    list_display = ('user', 'expires_in', 'facebook_user_id')
    raw_id_fields = ('user',)
    search_fields = ('user__email', 'facebook_user_id')


@admin.register(FacebookAccount)
class FacebookAccountAdmin(admin.ModelAdmin):
    list_display = ('account_name', 'account_id', 'config', 'last_sync')
    raw_id_fields = ('access',)
    search_fields = ('access__user__email', 'account_id', 'account_name')


@admin.register(FacebookAdCost)
class FacebookAdCostAdmin(admin.ModelAdmin):
    list_display = ('campaign_id', 'created_at', 'impressions', 'spend')
    raw_id_fields = ('account',)
    search_fields = ('account__access__user__email', 'account__account_id', 'campaign_id')


@admin.register(FulfillmentCost)
class FulfillmentCostAdmin(admin.ModelAdmin):
    list_display = ('order_id', 'source_id', 'total_cost', 'created_at')
    # raw_id_fields = ('store_object_id',)
    search_fields = ('order_id', 'source_id')


@admin.register(OtherCost)
class OtherCostAdmin(admin.ModelAdmin):
    list_display = ('date', 'amount')
    # raw_id_fields = ('store_object_id',)
    search_fields = ('date',)


@admin.register(ProfitSync)
class ProfitSyncAdmin(admin.ModelAdmin):
    list_display = ('store',)
    # raw_id_fields = ('store_object_id',)
    search_fields = ('store', 'date',)


@admin.register(ProfitOrder)
class ProfitOrderAdmin(admin.ModelAdmin):
    list_display = ('date', 'amount')
    raw_id_fields = ('sync',)
    search_fields = ('date',)


@admin.register(ProfitRefund)
class ProfitRefundAdmin(admin.ModelAdmin):
    list_display = ('date', 'amount')
    raw_id_fields = ('sync',)
    search_fields = ('date',)
