import arrow
import re
import csv
import mimetypes
from decimal import Decimal, ROUND_HALF_UP
from io import StringIO

from django.conf import settings
from django.conf.urls import url
from django.contrib import admin, messages
from django.contrib.admin import helpers
from django.db.models import Sum
from django.http import HttpResponse, HttpResponseRedirect
from django.template.response import TemplateResponse
from django.utils import timezone
from django.urls import reverse

from leadgalaxy.utils import aws_s3_upload
from .forms import ProductForm
from .models import (
    Category,
    Product,
    ProductPrice,
    CustomProduct,
    Order,
    OrderItem
)

admin.site.register(Category)


@admin.register(ProductPrice)
class ProductPriceAdmin(admin.ModelAdmin):
    list_display = ('sku', 'product', 'cost', 'target', 'retail')
    change_list_template = "prints/partial/admin_prices_change_list.html"
    search_fields = ('sku', 'product__title')

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            url(r'^import/prices/$', self.prints_import_prices, name="prints_import_prices"),
        ]
        return custom_urls + urls

    def prints_import_prices(self, request):
        csv_file = request.FILES.get('prices_csv')

        if not csv_file.name.endswith('.csv'):
            self.message_user(request, 'File is not CSV type', level=messages.ERROR)
            return HttpResponseRedirect(reverse('admin:prints_productprice_changelist'))

        key_gk_profit = 12
        key_total_profit = 9
        key_user_price = 6
        key_msrp = 4
        key_cost = 3

        # Read headers first
        reader = csv.reader(StringIO(csv_file.read().decode()))
        wrong_format = False
        for row in reader:
            if 'sku' in row[0].lower():  # Header found
                if row[key_gk_profit].strip() != 'GK Profit':
                    wrong_format = True
                elif row[key_total_profit].strip() != 'New Profit':
                    wrong_format = True
                elif row[key_user_price].strip() != 'New Price':
                    wrong_format = True
                elif row[key_msrp].strip() != 'MSRP':
                    wrong_format = True
                elif row[key_cost].strip() != 'Cost':
                    wrong_format = True
                break

        if wrong_format:
            self.message_user(request, 'Incorrect file format', level=messages.ERROR)
            return HttpResponseRedirect(reverse('admin:prints_productprice_changelist'))

        def fix_currency(amount):
            return ''.join(re.findall(r'[\d\.]+', amount)) or 0

        count = 0
        for row in reader:
            source_profit = Decimal(fix_currency(row[key_gk_profit]))
            dropified_profit = Decimal(fix_currency(row[key_total_profit])) - source_profit
            target = fix_currency(row[key_user_price])
            retail = fix_currency(row[key_msrp]) or None
            cost = fix_currency(row[key_cost])
            if dropified_profit <= 0 \
                    or not source_profit \
                    or not target \
                    or not cost:
                continue

            defaults = {
                'dropified_profit': dropified_profit,
                'source_profit': source_profit,
                'target': target,
                'cost': cost,
            }

            if retail:
                defaults['retail'] = retail

            skus = row[0].strip().split(' ')[0]
            for sku in skus.split('/'):
                count += 1
                ProductPrice.objects.update_or_create(
                    sku=sku,
                    defaults=defaults
                )

        self.message_user(request, f'{count} prices added/updated')
        return HttpResponseRedirect(reverse('admin:prints_productprice_changelist'))


class ProductPriceInline(admin.TabularInline):
    model = ProductPrice


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('title', 'source_type', 'source_id')
    ordering = ('id', 'source_id')
    search_fields = ('title', 'source_type', 'source_id', 'product_type__title')
    inlines = [ProductPriceInline]
    form = ProductForm

    def save_model(self, request, instance, form, change):
        if request.POST.get('dropified_image-clear'):
            instance.dropified_image = ''

        elif request.FILES.get('dropified_image'):
            image = request.FILES.get('dropified_image')
            extension = image.name.split('.')[-1]
            filename = f'uploads/layerapp/product/{instance.source_id}.{extension}'
            mimetype = mimetypes.guess_type(image.name)[0]

            instance.dropified_image = aws_s3_upload(
                filename=filename,
                fp=image,
                mimetype=mimetype,
                bucket_name=settings.S3_UPLOADS_BUCKET
            )

        instance.save()


@admin.register(CustomProduct)
class CustomProductAdmin(admin.ModelAdmin):
    list_display = ('title', 'product_type')
    ordering = ('id',)
    search_fields = ('id', 'user__id', 'user__email', 'title', 'description', 'product_type')


class DateFilter(admin.SimpleListFilter):
    date_format = 'MM/DD/YY'
    template = "prints/partial/admin_date_filter.html"

    def lookups(self, request, model_admin):
        def month_range(month):
            month = month.span('month')
            return f"{month[0].format(self.date_format)}-{month[1].format(self.date_format)}"

        this_month = arrow.now()
        last_month = arrow.now().replace(months=-1)
        return (
            (month_range(this_month), f"This month ({this_month.format('MMMM')})"),
            (month_range(last_month), f"Last month ({last_month.format('MMMM')})"),
        )

    def choices(self, changelist):
        # Grab only the "all" option.
        all_choice = next(super().choices(changelist))
        all_choice['query_parts'] = (
            (k, v)
            for k, v in changelist.get_filters_params().items()
            if k != self.parameter_name
        )
        yield all_choice

        use_custom_date = True
        for lookup, title in self.lookup_choices:
            is_selected = self.value() == str(lookup)
            if is_selected:
                use_custom_date = False
            yield {
                'selected': is_selected,
                'query_string': changelist.get_query_string({self.parameter_name: lookup}),
                'display': title,
            }

        if use_custom_date and self.value() is not None:
            yield {
                'selected': True,
                'query_string': changelist.get_query_string(),
                'display': 'Custom Range',
            }

    def queryset(self, request, queryset):
        lookup_value = request.GET.get(self.parameter_name)
        if lookup_value:
            date_range = lookup_value.split('-')
            if len(date_range) == 2:
                start, end = date_range

                return queryset.filter(**{
                    f"{self.parameter_name}__range": (
                        arrow.get(start, self.date_format).floor('day').datetime,
                        arrow.get(end, self.date_format).ceil('day').datetime
                    )
                })


class OrderDateFilter(DateFilter):
    title = 'Creation Date'
    parameter_name = 'created_at'


class OrderPayoutDateFilter(DateFilter):
    title = 'Payout Date'
    parameter_name = 'paid_at'


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    actions = ('pay_orders', 'export_orders')
    list_display = ('order_name', 'admin_source_id', 'admin_source_price', 'source_paid_reference', 'source_paid_at', 'paid_at')
    list_filter = (OrderDateFilter, OrderPayoutDateFilter)
    ordering = ('id',)
    search_fields = ('id', 'user__id', 'user__email', 'order_name', 'source_paid_reference')

    def admin_source_id(self, obj):
        return obj.id
    admin_source_id.admin_order_field = "id"
    admin_source_id.short_description = "LayerApp Order ID"

    def admin_source_price(self, obj):
        return obj.total_source_price
    admin_source_price.admin_order_field = "total_source_price"
    admin_source_price.short_description = "LayerApp Cost"

    def has_add_permission(self, request, obj=None):
        return False

    def get_queryset(self, request):
        qs = super().get_queryset(request)

        return qs.annotate(total_source_price=Sum('line_items__source_price'))

    def changelist_view(self, request, extra_context=None):
        # Hack for accepting empty _selected_action
        if request.POST.get('action') == 'pay_orders':
            if not request.POST.getlist(helpers.ACTION_CHECKBOX_NAME):
                post = request.POST.copy()
                post.setlist(helpers.ACTION_CHECKBOX_NAME, [0])
                request.POST = post

        return super().changelist_view(request, extra_context=extra_context)

    def pay_orders(self, request, queryset):
        order_ids = request.POST.getlist(helpers.ACTION_CHECKBOX_NAME)
        if request.POST.get('post'):
            queryset = self.model.objects.filter(id__in=order_ids)
            queryset.update(
                source_paid_at=timezone.now(),
                source_paid_reference=request.POST.get('source_paid_reference')
            )
            self.message_user(request, "Changed status on {} orders".format(queryset.count()))

            return HttpResponseRedirect(request.get_full_path())
        else:
            # Prevent already paid from being paid again
            queryset = queryset.filter(source_paid_at__isnull=True)

            total = queryset.aggregate(total=Sum('line_items__source_price'))['total']
            context = {
                'title': "Are you sure?",
                'queryset': queryset,
                'total': total,
                'action_checkbox_name': helpers.ACTION_CHECKBOX_NAME,
                'opts': self.model._meta
            }
            return TemplateResponse(request, 'prints/partial/admin_pay_orders.html', context)
    pay_orders.short_description = "Pay selected orders"

    def export_orders(self, request, queryset):
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="layerapp-orders.csv"'

        orders = queryset.annotate(
            total_source_price=Sum('line_items__source_price'),
            total_source_profit=Sum('line_items__source_profit'),
            total_dropified_price=Sum('line_items__dropified_price'),
            total_dropified_profit=Sum('line_items__dropified_profit'),
        )

        writer = csv.writer(response)
        writer.writerow([
            'Payout #',  # 1
            'Payout Date',  # 2
            'LayerApp Cost to us',  # 3
            'LayerApp Profit',  # 4
            'Dropified Cost to users',  # 5
            'Dropified Raw Profit',  # 6
            'Stripe Standard Fee',  # 7
            'LayerApp Order #',  # 8
            'Order #',  # 9
        ])

        for order in orders:
            stripe_fee = order.total_dropified_price * Decimal('.0299') + Decimal('.30')
            stripe_fee = stripe_fee.quantize(Decimal('.01'), ROUND_HALF_UP)

            paid_at = ''
            if order.source_paid_at:
                paid_at = order.source_paid_at.strftime('%c')

            writer.writerow([
                order.source_paid_reference,  # 1
                paid_at,  # 2
                order.total_source_price,  # 3
                order.total_source_profit,  # 4
                order.total_dropified_price,  # 5
                order.total_dropified_profit,  # 6
                stripe_fee,  # 7
                order.id,  # 8
                order.order_name,  # 9
            ])

        return response
    export_orders.short_description = "Export selected orders"


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    def has_add_permission(self, request, obj=None):
        return False
