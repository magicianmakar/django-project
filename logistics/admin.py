from django.contrib import admin
from django.utils.html import format_html

from .forms import AdminCarrierForm, OrderAdminForm
from .models import (
    Account,
    CarrierType,
    Carrier,
    Warehouse,
    Product,
    Variant,
    Supplier,
    Listing,
    Package,
    Order,
    OrderItem,
    AccountBalance,
    AccountCredit,
)


class CarrierInline(admin.TabularInline):
    extra = 1
    form = AdminCarrierForm
    model = Carrier

    def has_add_permission(self, request, obj):
        return False


@admin.register(Account)
class AccountAdmin(admin.ModelAdmin):
    inlines = (CarrierInline,)
    list_display = ('user', 'source_id', 'api_key', 'test_api_key')
    raw_id_fields = ('user',)
    search_fields = ('id', 'user__first_name', 'user__last_name', 'user__email', 'user_id')
    readonly_fields = ('balance',)

    def balance(self, obj):
        return f"${AccountBalance.objects.get(user=obj.user).balance:,.2f}"


@admin.register(AccountCredit)
class AccountCreditAdmin(admin.ModelAdmin):
    search_fields = (
        'id',
        'balance__user__first_name',
        'balance__user__last_name',
        'balance__user__email',
        'balance__user_id',
    )
    readonly_fields = ('stripe_charge_id',)


class AccountCreditInline(admin.TabularInline):
    extra = 1
    model = AccountCredit


@admin.register(AccountBalance)
class AccountBalanceAdmin(admin.ModelAdmin):
    inlines = (AccountCreditInline,)
    raw_id_fields = ('user',)
    search_fields = ('id', 'user__first_name', 'user__last_name', 'user__email', 'user_id')


@admin.register(CarrierType)
class CarrierTypeAdmin(admin.ModelAdmin):
    list_display = ('logo', 'label', 'name', 'source')
    search_fields = ('label', 'name', 'source')

    def logo(self, obj):
        return format_html(f'<img src="{obj.logo_url}" style="max-width: 100px;max-height:50px;">')


@admin.register(Carrier)
class CarrierAdmin(admin.ModelAdmin):
    list_display = ('account', 'carrier_type')
    search_fields = (
        'id',
        'account__user__first_name',
        'account__user__last_name',
        'account__user__email',
        'account__user_id',
    )


class PaidFilter(admin.SimpleListFilter):
    title = 'is paid'
    parameter_name = 'is_paid'

    def lookups(self, request, model_admin):
        return (
            ('0', 'Paid'),
            ('1', 'Unpaid'),
        )

    def queryset(self, request, queryset):
        value = self.value()
        if value:
            value = True if value == '1' else False
            return queryset.filter(paid_at__isnull=value)


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('store_id', 'store_order_number', 'paid_at', 'carrier', 'service', 'weight', 'shipment_cost', 'warehouse')
    list_filter = (PaidFilter, 'store_type', 'refund_status')
    search_fields = (
        'store_id',
        'store_order_number',
        'paid_at',
        'carrier',
        'rate_id',
        'service',
        'weight',
        'warehouse__id',
        'warehouse__user__id',
        'warehouse__user__email',
        'warehouse__user__username',
    )

    form = OrderAdminForm


admin.site.register(Warehouse)
admin.site.register(Product)
admin.site.register(Variant)
admin.site.register(Supplier)
admin.site.register(Listing)
admin.site.register(Package)
admin.site.register(OrderItem)
