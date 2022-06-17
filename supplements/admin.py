import csv
from decimal import Decimal

from django.contrib import admin, messages
from django.contrib.admin import helpers
from django.db.models import Sum
from django.http import HttpResponse, HttpResponseRedirect
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import format_html

from lib.exceptions import capture_exception

from .forms import ShippingGroupAdminForm
from .lib.shipstation import create_shipstation_order, get_shipstation_order
from .models import (
    AuthorizeNetCustomer,
    BasketItem,
    BasketOrder,
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
    UserSupplementLabel,
    UserUnpaidOrder
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
    search_fields = ('title', 'shipstation_sku')
    list_filter = ('is_active', 'is_discontinued', 'label_size', 'mockup_type')


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
        'get_shipstation_key',
        'status',
        'store_type',
        'store_id',
        'store_order_id',
        'amount',
        'sale_price',
        'user',
        'created_at',
        'payment_date',
        'wholesale_price',
    )
    raw_id_fields = ('user',)
    readonly_fields = ('payment_date',)
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

    def get_shipstation_key(self, obj):
        if obj.shipstation_key:
            return obj.shipstation_key
        else:
            return format_html(f'<a href="{reverse("admin:shipstation_sync", kwargs={"order_id": obj.pk})}">Sync Shipstation</a>')

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('shipstation/sync/<int:order_id>', self.shipstation_sync, name='shipstation_sync'),
        ]
        return custom_urls + urls

    def shipstation_sync(self, request, order_id):
        pls_order = PLSOrder.objects.get(id=order_id)
        if pls_order.order_items.count() == 0:
            return HttpResponse('There are no items in that order')

        shipstation_order = get_shipstation_order(pls_order.shipstation_order_number)
        if shipstation_order:
            pls_order.shipstation_key = shipstation_order['orderKey']
            pls_order.save()
            return HttpResponseRedirect(reverse('admin:supplements_plsorder_changelist'))

        if request.GET.get('notcreate'):
            return HttpResponseRedirect(reverse('admin:supplements_plsorder_changelist'))

        try:
            create_shipstation_order(pls_order)
        except:
            capture_exception()
            return HttpResponse(status=500)

        return HttpResponseRedirect(reverse('admin:supplements_plsorder_changelist'))

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
        'supplier',
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
    search_fields = ('name',)


@admin.register(LabelSize)
class LabelSizeAdmin(admin.ModelAdmin):
    list_display = ('size',)


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


@admin.register(BasketItem)
class BasketItemAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'user',
        'user_supplement',
        'quantity',
        'created_at',
    )
    raw_id_fields = ('user', 'user_supplement')


@admin.register(BasketOrder)
class BasketOrderAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'user',
        'status',
        'created_at',
    )
    raw_id_fields = ('user',)


@admin.register(UserUnpaidOrder)
class UserUnpaidOrderAdmin(admin.ModelAdmin):
    list_display = ('email', 'total_amount',)
    change_form_template = 'supplements/admin/user_unpaid_order_change_form.html'

    def has_delete_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_add_permission(self, request):
        return False

    def get_urls(self):
        from django.urls import path
        urls = super().get_urls()
        my_urls = [
            path('charge-customer-all/<int:user_id>/', self.charge_customer_all, name="charge-customer-all"),
        ]
        return my_urls + urls

    def validate_customer(self, request, user):
        try:
            user.authorize_net_customer.retrieve()
        except AuthorizeNetCustomer.DoesNotExist:
            self.message_user(request, 'Customer without payment profile', level=messages.ERROR)
            return False

        if not user.authorize_net_customer.payment_id:
            self.message_user(request, 'Customer without payment profile', level=messages.ERROR)
            return False

        return True

    def charge_customer_all(self, request, user_id):
        user = UserUnpaidOrder.objects.get(pk=user_id)
        if not self.validate_customer(request, user):
            return HttpResponseRedirect(reverse('admin:supplements_userunpaidorder_changelist'))

        order_numbers = []
        order_ids = []
        line_item = dict(id='', name='Past Orders', quantity=1, unit_price=Decimal('0'))
        for order in user.unpaid_orders:
            order_numbers.append(order.order_number)
            order_ids.append(order.id)
            line_item['unit_price'] += order.amount

        line_item['id'] = f"{order_numbers[0]}-{order_numbers[-1]}"
        transaction_id = user.authorize_net_customer.charge(
            line_item['unit_price'],
            line_item
        )

        if transaction_id:
            PLSOrder.objects.filter(id__in=order_ids).update(
                stripe_transaction_id=transaction_id,
                payment_date=timezone.now()
            )
            self.message_user(request, f"Charged customer {user.email} for Order IDs: {order_ids}")
        else:
            self.message_user(request, f'Error trying to charge customer {user.email}', level=messages.ERROR)
        return HttpResponseRedirect(reverse('admin:supplements_userunpaidorder_changelist'))
