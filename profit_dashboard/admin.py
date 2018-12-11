from django.contrib import admin
from .models import (
    FacebookAccess,
    FacebookAccount,
    FacebookAdCost,
    AliexpressFulfillmentCost,
    OtherCost,
)


@admin.register(FacebookAccess)
class FacebookAccessAdmin(admin.ModelAdmin):
    list_display = ('store', 'expires_in', 'facebook_user_id')
    raw_id_fields = ('store', 'user')
    search_fields = ('store__shop', 'user__email', 'facebook_user_id')


@admin.register(FacebookAccount)
class FacebookAccountAdmin(admin.ModelAdmin):
    list_display = ('account_name', 'account_id', 'config', 'last_sync')
    raw_id_fields = ('store', 'access')
    search_fields = ('access__store__shop', 'account_id', 'account_name')


@admin.register(FacebookAdCost)
class FacebookAdCostAdmin(admin.ModelAdmin):
    list_display = ('campaign_id', 'created_at', 'impressions', 'spend')
    raw_id_fields = ('account',)
    search_fields = ('account__access__store__shop', 'account__account_id', 'campaign_id')


@admin.register(AliexpressFulfillmentCost)
class AliexpressFulfillmentCostAdmin(admin.ModelAdmin):
    list_display = ('order_id', 'source_id', 'total_cost', 'created_at')
    raw_id_fields = ('store',)
    search_fields = ('store__shop', 'order_id', 'source_id')


@admin.register(OtherCost)
class OtherCostAdmin(admin.ModelAdmin):
    list_display = ('store', 'date', 'amount')
    raw_id_fields = ('store',)
    search_fields = ('store__shop', 'date')
