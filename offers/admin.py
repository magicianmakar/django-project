import arrow
from django.contrib import admin
from django.contrib.admin import filters
from django.contrib.auth.models import User
from django.db.models import Q, Count, Sum, Prefetch
from django.urls import reverse
from django.utils.html import format_html

from shopified_core.utils import app_link
from stripe_subscription.stripe_api import stripe
from .models import OfferCustomer, OfferCoupon, Offer


class DateRangeFilter(filters.DateFieldListFilter):
    template = 'admin/offers/date_range_filter.html'

    def __init__(self, field, request, *args, **kwargs):
        self.parameter_name = kwargs.get('field_path')

        self.lt = {'name': f"{self.parameter_name}__lt"}
        self.gte = {'name': f"{self.parameter_name}__gte"}
        self.lt['value'] = request.GET.get(self.lt['name'], '').split(' ')[0]
        self.gte['value'] = request.GET.get(self.gte['name'], '').split(' ')[0]

        super().__init__(field, request, *args, **kwargs)

    def queryset(self, request, queryset):
        date__lt = self.used_parameters.get(self.lt['name'])
        if date__lt:
            self.used_parameters[self.lt['name']] = arrow.get(date__lt).ceil('day').datetime

        date__gte = self.used_parameters.get(self.gte['name'])
        if date__gte:
            self.used_parameters[self.gte['name']] = arrow.get(date__gte).floor('day').datetime

        query_filter = Q()
        for key in list(self.used_parameters.keys()):
            if 'offercustomer__' in key:
                value = self.used_parameters[key]
                query_filter &= Q(**{key.replace('offercustomer__', ''): value})
                del self.used_parameters[key]

        return queryset.prefetch_related(Prefetch('offercustomer_set',
                                                  OfferCustomer.objects.filter(query_filter),
                                                  to_attr="offercustomers"))


class OwnerFilter(filters.SimpleListFilter):
    title = 'Owner'
    parameter_name = 'owner'

    def lookups(self, request, model_admin):
        user_ids = model_admin.get_queryset(request).values_list('owner_id', flat=True)
        return [[u.id, u.first_name] for u in User.objects.filter(id__in=user_ids)]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(owner_id=self.value())
        return queryset


@admin.register(Offer)
class OfferAdmin(admin.ModelAdmin):
    exclude = ('owner',)
    list_display = ('title', 'owner', 'plan', 'get_addons_count', 'coupon', 'get_total_customers', 'get_total_amount', 'link_actions')
    prepopulated_fields = {'slug': ('title',)}
    change_list_template = 'admin/offers/offer/change_list.html'
    list_filter = (('offercustomer__created_at', DateRangeFilter), OwnerFilter)

    def get_total_customers(self, obj):
        return len(obj.offercustomers)
    get_total_customers.short_description = 'Total Customers'

    def get_total_amount(self, obj):
        return sum([uc.amount for uc in obj.offercustomers])
    get_total_amount.short_description = 'Total Amount'

    def get_addons_count(self, obj):
        return obj.billings.count()
    get_addons_count.short_description = 'Addons Count'

    def link_actions(self, obj):
        url = app_link(reverse('offers:details', kwargs={
            'pk': obj.id,
            'slug': obj.slug,
            'seller_id': self.request.user.id
        }))

        permalink = f"""
            <a href="#" onclick="this.children[0].style.display='';
                                 this.children[0].select();
                                 document.execCommand('copy');
                                 this.children[0].style.display='none'">
                Copy Customer Link
                <input type="text" style="display: none;"
                       value="{url}">
            </a>
        """
        return format_html(permalink)
    link_actions.allow_tags = True
    link_actions.short_description = 'Actions'

    def save_model(self, request, obj, form, change):
        if not obj.owner_id:
            obj.owner_id = request.user.id
        super().save_model(request, obj, form, change)

    def changelist_view(self, request, extra_context=None):
        self.request = request
        search_filters = {}
        for param in request.GET.keys():
            if 'offercustomer' in param:
                search_filters[param.replace('offercustomer__', '')] = request.GET[param]

        search_filters['created_at__lt'] = arrow.get(
            search_filters.get('created_at__lt', arrow.get())
        ).ceil('day').datetime

        search_filters['offer_id__in'] = list(self.get_queryset(request).values_list('id', flat=True))
        customers = OfferCustomer.objects.filter(**search_filters).extra({
            'date_key': 'date(created_at)'
        }).values('date_key', 'seller__first_name').annotate(
            customer_count=Count('id'),
            amount_sum=Sum('amount')
        )

        extra_context = extra_context or {}
        extra_context['graph_labels'] = []
        extra_context['customer_graph'] = []
        extra_context['amount_graph'] = []
        if customers:
            data = {}
            for customer in customers:
                customer_label = customer['seller__first_name']
                if not data.get(customer_label):
                    data[customer_label] = {
                        'label': customer_label,
                        'raw_data': {},
                        'data': [],
                        'amount_data': []
                    }

                data[customer_label]['raw_data'][customer['date_key']] = {
                    'customers': customer['customer_count'],
                    'amount': customer['amount_sum'],
                }

            start = arrow.get(search_filters.get('created_at__gte', customers[0]['date_key']))
            end = arrow.get(search_filters['created_at__lt'])
            date_format = 'MMM D, YYYY'
            extra_context['chart_date'] = '{}'
            if start.year == end.year:
                date_format = date_format.replace(', YYYY', '')
                extra_context['chart_date'] = start.format('{}, YYYY')
            if start.month == end.month:
                date_format = date_format.replace('MMM ', '')
                extra_context['chart_date'] = start.format('MMM {}, YYYY')

            for day in arrow.Arrow.range('day', start, end):
                extra_context['graph_labels'].append(day.format(date_format))

                for owner in data:
                    if data[owner]['raw_data'].get(day.date()):
                        data[owner]['data'].append(data[owner]['raw_data'][day.date()]['customers'])
                        data[owner]['amount_data'].append(data[owner]['raw_data'][day.date()]['amount'])
                    else:
                        data[owner]['data'].append(0)
                        data[owner]['amount_data'].append(0)

            for owner in data:
                del data[owner]['raw_data']
                extra_context['customer_graph'].append({
                    'label': f"{data[owner]['label']} - {sum(data[owner]['data'])}",
                    'data': data[owner]['data'],
                })
                extra_context['amount_graph'].append({
                    'label': f"{data[owner]['label']} - {sum(data[owner]['amount_data'])}",
                    'data': data[owner]['amount_data'],
                })

        return super().changelist_view(request, extra_context=extra_context)


@admin.register(OfferCoupon)
class OfferCouponAdmin(admin.ModelAdmin):
    delete_confirmation_template = 'admin/offers/offercoupon/delete_confirmation.html'
    delete_selected_confirmation_template = 'admin/offers/offercoupon/delete_selected_confirmation.html'

    def save_model(self, request, obj, form, change):
        if not obj.stripe_coupon_id and not change:
            coupon = stripe.Coupon.create(**obj.to_stripe_dict())
            obj.stripe_coupon_id = coupon.id
        super().save_model(request, obj, form, change)

    def delete_model(self, request, obj):
        stripe.Coupon.delete(obj.stripe_coupon_id)
        super().delete_model(request, obj)

    def has_change_permission(self, request, obj=None):
        return False
