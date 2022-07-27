from django.contrib import admin
from django.utils.html import format_html

from .forms import AdminCarrierForm
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


admin.site.register(Warehouse)
admin.site.register(Product)
admin.site.register(Variant)
admin.site.register(Supplier)
admin.site.register(Listing)
admin.site.register(Package)
admin.site.register(Order)
admin.site.register(OrderItem)
