from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html

from .models import AlibabaAccount, AlibabaOrder, AlibabaOrderItem


@admin.register(AlibabaAccount)
class AlibabaAccountAdmin(admin.ModelAdmin):
    list_display = ('get_user_email', 'alibaba_user_id', 'access_token', 'expired_at')
    search_fields = ('user__id', 'user__email', 'alibaba_user_id', 'access_token', 'ecology_token')
    raw_id_fields = ('user',)

    def get_user_email(self, obj):
        return obj.user.email


@admin.register(AlibabaOrder)
class AlibabaOrderAdmin(admin.ModelAdmin):
    list_display = ('id', 'trade_id', 'source_status', 'products_cost', 'shipping_cost', 'store_type', 'get_alibaba_account', 'get_user_email')
    search_fields = (
        'trade_id',
        'order_data_ids',
        'user__id',
        'user__email',
        'order__user__alibaba__id',
        'order__user__alibaba__alibaba_user_id',
    )
    list_filter = ('source_status',)
    raw_id_fields = ('user',)

    def get_user_email(self, obj):
        return obj.user.email
    get_user_email.allow_tags = True
    get_user_email.short_description = 'User E-mail'

    def get_alibaba_account(self, obj):
        account = obj.user.alibaba.first()
        if account:
            account_url = reverse('admin:alibaba_core_alibabaaccount_change', args=(account.id,))
            return format_html(f'<a href="{account_url}">{account.alibaba_user_id}</a>')
        return 'Not Found'
    get_alibaba_account.allow_tags = True
    get_alibaba_account.short_description = 'Alibaba Account'


@admin.register(AlibabaOrderItem)
class AlibabaOrderItemAdmin(admin.ModelAdmin):
    list_display = ('id', 'get_trade_id', 'source_tracking', 'product_id', 'is_bundled', 'get_alibaba_account', 'get_user_email')
    list_filter = ('is_bundled',)
    search_fields = (
        'product_id',
        'variant_id',
        'source_tracking',
        'order__user__id',
        'order__user__email',
        'order__user__alibaba__id',
        'order__user__alibaba__alibaba_user_id',
        'order__trade_id',
    )
    raw_id_fields = ('order',)

    def get_user_email(self, obj):
        return obj.order.user.email
    get_user_email.allow_tags = True
    get_user_email.short_description = 'User E-mail'

    def get_trade_id(self, obj):
        return obj.order.trade_id
    get_trade_id.allow_tags = True
    get_trade_id.short_description = 'Trade ID'

    def get_alibaba_account(self, obj):
        account = obj.order.user.alibaba.first()
        if account:
            account_url = reverse('admin:alibaba_core_alibabaaccount_change', args=(account.id,))
            return format_html(f'<a href="{account_url}">{account.alibaba_user_id}</a>')
        return 'Not Found'
    get_alibaba_account.allow_tags = True
    get_alibaba_account.short_description = 'Alibaba Account'
