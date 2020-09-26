# -*- coding: utf-8 -*-
import csv
from django.contrib import admin
from django.contrib.admin import helpers
from django.db.models import Sum
from django.http import HttpResponse

from .forms import ShippingGroupAdminForm
from .models import (
    AuthorizeNetCustomer,
    LabelComment,
    LabelSize,
    MockupType,
    Payout,
    PLSOrder,
    PLSOrderLine,
    PLSupplement,
    RefundPayments,
    ShippingGroup,
    UserSupplement,
    UserSupplementImage,
    UserSupplementLabel
)


@admin.register(PLSupplement)
class PLSupplementAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'title',
        'description',
        'category',
        'tags',
        'shipstation_sku',
        'cost_price',
        'label_template_url',
        'wholesale_price',
        'weight',
        'inventory',
        'approved_label_url',
    )


@admin.register(UserSupplement)
class UserSupplementAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'title',
        'description',
        'category',
        'tags',
        'shipstation_sku',
        'user',
        'pl_supplement',
        'price',
        'compare_at_price',
        'created_at',
    )
    raw_id_fields = ('user', 'pl_supplement')


@admin.register(UserSupplementLabel)
class UserSupplementLabelAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'user_supplement',
        'status',
        'url',
        'sku',
        'created_at',
        'updated_at',
    )
    list_filter = ('created_at', 'updated_at')
    raw_id_fields = ('user_supplement',)
    date_hierarchy = 'created_at'


@admin.register(UserSupplementImage)
class UserSupplementImageAdmin(admin.ModelAdmin):
    list_display = ('id', 'user_supplement', 'position', 'image_url')
    raw_id_fields = ('user_supplement',)


@admin.register(LabelComment)
class LabelCommentAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'label',
        'user',
        'text',
        'new_status',
        'created_at',
    )
    raw_id_fields = ('label', 'user')


class OrderPaidFilter(admin.SimpleListFilter):
    title = 'Payment Status'
    parameter_name = 'payment_status'

    def lookups(self, request, model_admin):
        return (
            ('paid', 'Paid'),
            ('unpaid', 'Not Paid'),
        )

    def queryset(self, request, queryset):
        if self.value() == 'unpaid':
            return queryset.filter(stripe_transaction_id='')
        if self.value() == 'paid':
            return queryset.exclude(stripe_transaction_id='')


@admin.register(PLSOrder)
class PLSOrderAdmin(admin.ModelAdmin):
    list_filter = (OrderPaidFilter,)
    search_fields = ('user__id', 'user__email')
    list_display = (
        'id',
        'order_number',
        'stripe_transaction_id',
        'shipstation_key',
        'store_type',
        'store_id',
        'store_order_id',
        'amount',
        'sale_price',
        'status',
        'user',
        'created_at',
        'payment_date',
        'wholesale_price',
    )
    raw_id_fields = ('user',)
    readonly_fields = ('stripe_transaction_id', 'payment_date')
    actions = ('export_order_lines', 'export_orders', 'export_totals_by_user')

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        # Hack for accepting empty _selected_action
        if request.POST.get('action') in self.actions:
            if not request.POST.getlist(helpers.ACTION_CHECKBOX_NAME):
                post = request.POST.copy()
                post.setlist(helpers.ACTION_CHECKBOX_NAME, [0])
                post['select_across'] = True
                request.POST = post

        return super().changelist_view(request, extra_context=extra_context)

    def export_order_lines(self, request, queryset):
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="detailed-order-lines.csv"'

        writer = csv.writer(response)
        writer.writerow([
            'User ID',
            'Order ID',  # 1
            'Line ID',  # 2
            'Supplement',  # 3
            'Total Cost',  # 4
        ])

        orders = queryset.prefetch_related(
            'order_items',
            'order_items__label',
            'order_items__label__user_supplement',
        )
        for order in orders:
            for item in order.order_items.all():
                writer.writerow([
                    order.user_id,
                    order.order_number,
                    item.line_id,
                    f'{item.quantity} x {item.label.user_supplement.title} (${item.amount / 100.:.2f})',
                    f'${((item.amount * item.quantity) / 100.):.2f}'
                ])

        return response
    export_order_lines.short_description = "Export Line Items"

    def export_orders(self, request, queryset):
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="orders.csv"'

        writer = csv.writer(response)
        # order id, quantity x supplement, total cost
        writer.writerow([
            'User ID',
            'Order ID',
            'Status',
            'Transaction ID',
            'Payout Id',
            'Shipstation Key',
            'Sale Price',
            'Wholesale Price',
            'Shipping Price',
            'Amount ( In USD )',
            'Raw Amount',
        ])

        for order in queryset:
            writer.writerow([
                order.user_id,
                order.order_number,
                order.status,
                order.stripe_transaction_id,
                order.payout_id,
                order.shipstation_key,
                f'${(order.sale_price / 100.):.2f}',
                f'${(order.wholesale_price / 100.):.2f}',
                f'${(order.shipping_price / 100.):.2f}',
                f'${((order.amount) / 100.):.2f}',
                order.amount,
            ])

        return response
    export_orders.short_description = "Export Orders"

    def export_totals_by_user(self, request, queryset):
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="total-orders-by-user.csv"'
        writer = csv.writer(response)
        writer.writerow([
            'User E-mail',
            'Total Amount',
        ])

        for result in queryset.values('user__email').annotate(total=Sum('amount')).order_by('user__email'):
            writer.writerow([
                result['user__email'],
                f"${((result['total']) / 100.):.2f}",
            ])

        return response
    export_totals_by_user.short_description = "Export Totals by User"


@admin.register(PLSOrderLine)
class PLSOrderLineAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'store_type',
        'store_id',
        'store_order_id',
        'line_id',
        'label',
        'shipstation_key',
        'pls_order',
        'amount',
        'quantity',
        'sale_price',
        'is_label_printed',
        'created_at',
        'wholesale_price',
    )
    raw_id_fields = ('pls_order', 'label')


@admin.register(Payout)
class PayoutAdmin(admin.ModelAdmin):
    list_display = (
        'reference_number',
        'created_at',
        'status',
    )


@admin.register(AuthorizeNetCustomer)
class AuthorizeNetCustomer(admin.ModelAdmin):
    list_display = (
        'customer_id',
        'payment_id',
        'created_at',
        'updated_at',
    )
    raw_id_fields = ('user',)


@admin.register(ShippingGroup)
class ShippingGroupAdmin(admin.ModelAdmin):
    form = ShippingGroupAdminForm
    list_display = (
        'slug',
        'name',
        'locations',
        'immutable',
    )


@admin.register(LabelSize)
class LabelSizeAdmin(admin.ModelAdmin):
    list_display = (
        'slug',
        'height',
        'width',
    )


@admin.register(MockupType)
class MockupTypeAdmin(admin.ModelAdmin):
    list_display = (
        'slug',
        'name',
    )


@admin.register(RefundPayments)
class RefundPaymentsAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'amount',
        'fee',
        'transaction_id',
        'created_at',
    )
