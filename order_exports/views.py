import arrow
import simplejson as json

from django.core.exceptions import PermissionDenied
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.core.urlresolvers import reverse
from django.contrib.auth.models import User
from django.contrib import messages
from django.http import JsonResponse

from order_exports.api import ShopifyOrderExportAPI
from order_exports.forms import OrderExportForm
from order_exports.models import *


@login_required
def index(request):
    if request.user.is_vendor:
        order_exports = OrderExport.objects.filter(vendor_user__user=request.user.pk)
        vendor_users = OrderExportVendor.objects.filter(user=request.user.pk)
    else:
        if not request.user.can('orders.use'):
            raise PermissionDenied()

        order_exports = OrderExport.objects.filter(store__user=request.user.pk)
        vendor_users = OrderExportVendor.objects.filter(owner=request.user.pk)

    breadcrumbs = ['Order Exports']

    return render(request, 'order_exports/index.html', {
        'order_exports': order_exports, 'page': "order_exports",
        'breadcrumbs': breadcrumbs, 'vendor_users': vendor_users
    })


@login_required
def add(request):
    if not request.user.can('orders.use'):
        raise PermissionDenied()
    else:
        if not request.user.can('orders.view'):
            raise PermissionDenied()

    breadcrumbs = [{'title': 'Order Exports', 'url': reverse('order_exports_index')}, 'Add']
    form = OrderExportForm()

    fields = DEFAULT_FIELDS
    fields_choices = DEFAULT_FIELDS_CHOICES
    shipping_address = DEFAULT_SHIPPING_ADDRESS
    shipping_address_choices = DEFAULT_SHIPPING_ADDRESS_CHOICES
    line_fields = DEFAULT_LINE_FIELDS
    line_fields_choices = DEFAULT_LINE_FIELDS_CHOICES
    product_titles = ['']
    found_products = "[]"

    if request.method == 'POST':
        product_titles = request.POST.getlist('product_title')
        found_products = request.POST.get('found_products')
        form = OrderExportForm(request.POST)

        fields = json.loads(request.POST.get('fields', '[]'))
        fields, fields_choices = fix_fields(
            fields,
            ORDER_FIELD_CHOICES,
            prefix='fields_'
        )

        shipping_address = json.loads(request.POST.get('shipping_address', '[]'))
        shipping_address, shipping_address_choices = fix_fields(
            shipping_address,
            ORDER_SHIPPING_ADDRESS_CHOICES,
            prefix='shipping_address_'
        )

        line_fields = json.loads(request.POST.get('line_fields', '[]'))
        line_fields, line_fields_choices = fix_fields(
            line_fields,
            ORDER_LINE_FIELD_CHOICES,
            prefix='line_fields_'
        )

        if form.is_valid():
            daterange = request.POST.get('daterange') or ' - '
            created_at_min, created_at_max = daterange.split(' - ')

            tz = timezone.localtime(timezone.now()).strftime(' %z')

            if created_at_min:
                created_at_min = arrow.get(created_at_min + tz, r'MM/DD/YYYY Z').datetime
            if created_at_max:
                created_at_max = arrow.get(created_at_max + tz, r'MM/DD/YYYY Z').datetime

            vendor_user_id = create_vendor_user(request)
            if vendor_user_id is not None:
                filters = OrderExportFilter.objects.create(
                    vendor=request.POST.get('vendor'),
                    status=request.POST.get('status'),
                    fulfillment_status=request.POST.get('fulfillment_status'),
                    financial_status=request.POST.get('financial_status'),
                    created_at_min=created_at_min or None,
                    created_at_max=created_at_max or None,
                    product_price_min=request.POST.get('product_price_min') or None,
                    product_price_max=request.POST.get('product_price_max') or None,
                    product_title=','.join(product_titles) or None
                )

                order_export = OrderExport.objects.create(
                    store_id=request.POST.get('store'),
                    schedule=request.POST.get('schedule') or None,
                    receiver=request.POST.get('receiver'),
                    description=request.POST.get('description'),
                    previous_day=request.POST.get('previous_day', False) == 'on',
                    fields=json.dumps(fields),
                    shipping_address=json.dumps(shipping_address),
                    line_fields=json.dumps(line_fields),
                    filters=filters,
                    vendor_user_id=vendor_user_id,
                    starting_at=form.cleaned_data['starting_at']
                )

                order_export.save()

                for found_product in json.loads(found_products):
                    OrderExportFoundProduct.objects.create(order_export=order_export,
                                                           image_url=found_product.get('image_url'),
                                                           title=found_product.get('title'),
                                                           product_id=found_product.get('product_id'))

                order_export.send_done_signal()

                messages.success(request, 'Created order exports successfuly')
                return redirect(reverse('order_exports_index'))

    vendor_users = User.objects.filter(profile__subuser_parent=request.user)

    return render(request, 'order_exports/add.html', {
        'form': form,
        'page': "order_exports",
        'order_status': ORDER_STATUS,
        'order_fulfillment_status': ORDER_FULFILLMENT_STATUS,
        'order_financial_status': ORDER_FINANCIAL_STATUS,
        'order_fields': ORDER_FIELD_CHOICES,
        'order_line_fields': ORDER_LINE_FIELD_CHOICES,
        'order_shipping_address': ORDER_SHIPPING_ADDRESS_CHOICES,
        'selected_fields': fields,
        'fields_choices': fields_choices,
        'selected_shipping_address': shipping_address,
        'shipping_address_choices': shipping_address_choices,
        'selected_line_fields': line_fields,
        'line_fields_choices': line_fields_choices,
        'breadcrumbs': breadcrumbs,
        'vendor_users': vendor_users,
        'product_titles': product_titles,
        'found_products': found_products,
    })


@login_required
def edit(request, order_export_id):
    if not request.user.can('orders.use'):
        raise PermissionDenied()

    order_export = get_object_or_404(OrderExport, pk=order_export_id,
                                     store__user_id=request.user.id)

    if order_export.filters.product_title is not None:
        product_titles = order_export.filters.product_title.split(',')
    else:
        product_titles = ['']

    breadcrumbs = [
        {'title': 'Order Exports', 'url': reverse('order_exports_index')},
        {'title': order_export.description, 'url': reverse('order_exports_edit', kwargs={'order_export_id': order_export.id})},
        'Edit'
    ]

    form = OrderExportForm(initial={
        "previous_day": order_export.previous_day,
        "copy_me": order_export.copy_me,
        "vendor_user": order_export.vendor_user and order_export.vendor_user.pk or None,
        "product_price_min": order_export.filters.product_price_min,
        "product_price_max": order_export.filters.product_price_max,
        "starting_at": order_export.starting_at,
    })

    fields = order_export.fields_data
    fields_choices = order_export.fields_choices
    shipping_address = order_export.shipping_address_data
    shipping_address_choices = order_export.shipping_address_choices
    line_fields = order_export.line_fields_data
    line_fields_choices = order_export.line_fields_choices
    found_products = order_export.json_found_products

    if request.method == 'POST':
        product_titles = request.POST.getlist('product_title')
        found_products = request.POST.get('found_products')
        form = OrderExportForm(request.POST)

        fields = json.loads(request.POST.get('fields', '[]'))
        fields, fields_choices = fix_fields(
            fields,
            ORDER_FIELD_CHOICES,
            prefix='fields_'
        )

        shipping_address = json.loads(request.POST.get('shipping_address', '[]'))
        shipping_address, shipping_address_choices = fix_fields(
            shipping_address,
            ORDER_SHIPPING_ADDRESS_CHOICES,
            prefix='shipping_address_'
        )

        line_fields = json.loads(request.POST.get('line_fields', '[]'))
        line_fields, line_fields_choices = fix_fields(
            line_fields,
            ORDER_LINE_FIELD_CHOICES,
            prefix='line_fields_'
        )

        if form.is_valid():
            vendor_user_id = create_vendor_user(request)
            if vendor_user_id is not None:
                order_export.store_id = request.POST.get('store')
                order_export.schedule = request.POST.get('schedule') or None
                order_export.receiver = request.POST.get('receiver')
                order_export.description = request.POST.get('description')
                order_export.previous_day = request.POST.get('previous_day', False) == 'on'
                order_export.vendor_user_id = vendor_user_id
                order_export.starting_at = form.cleaned_data['starting_at']

                order_export.fields = json.dumps(fields)
                order_export.shipping_address = json.dumps(shipping_address)
                order_export.line_fields = json.dumps(line_fields)

                daterange = request.POST.get('daterange') or ' - '
                created_at_min, created_at_max = daterange.split(' - ')
                tz = timezone.localtime(timezone.now()).strftime(' %z')

                if created_at_min:
                    created_at_min = arrow.get(created_at_min + tz, r'MM/DD/YYYY Z').datetime
                if created_at_max:
                    created_at_max = arrow.get(created_at_max + tz, r'MM/DD/YYYY Z').datetime

                filters = order_export.filters
                filters.vendor = request.POST.get('vendor')
                filters.status = request.POST.get('status')
                filters.fulfillment_status = request.POST.get('fulfillment_status')
                filters.financial_status = request.POST.get('financial_status')
                filters.created_at_min = created_at_min or None
                filters.created_at_max = created_at_max or None
                filters.product_price_min = request.POST.get('product_price_min') or None
                filters.product_price_max = request.POST.get('product_price_max') or None
                filters.product_title = ','.join(product_titles) or None

                filters.save()
                order_export.save()

                order_export.found_products.all().delete()
                for found_product in json.loads(found_products):
                    OrderExportFoundProduct.objects.create(order_export=order_export,
                                                           image_url=found_product.get('image_url'),
                                                           title=found_product.get('title'),
                                                           product_id=found_product.get('product_id'))

                order_export.send_done_signal()

                messages.success(request, 'Edited order exports successfuly')
                return redirect(reverse('order_exports_index'))

    vendor_users = User.objects.filter(profile__subuser_parent=request.user)

    return render(request, 'order_exports/edit.html', {
        'order_export': order_export,
        'form': form,
        'page': "order_exports",
        'order_status': ORDER_STATUS,
        'order_fulfillment_status': ORDER_FULFILLMENT_STATUS,
        'order_financial_status': ORDER_FINANCIAL_STATUS,
        'order_fields': ORDER_FIELD_CHOICES,
        'order_line_fields': ORDER_LINE_FIELD_CHOICES,
        'order_shipping_address': ORDER_SHIPPING_ADDRESS_CHOICES,
        'selected_fields': fields,
        'fields_choices': fields_choices,
        'selected_shipping_address': shipping_address,
        'shipping_address_choices': shipping_address_choices,
        'selected_line_fields': line_fields,
        'line_fields_choices': line_fields_choices,
        'breadcrumbs': breadcrumbs,
        'vendor_users': vendor_users,
        'product_titles': product_titles,
        'found_products': found_products,
    })


@login_required
def delete(request, order_export_id):
    order_export = get_object_or_404(OrderExport, pk=order_export_id,
                                     store__user_id=request.user.id)
    order_export.delete()

    return redirect('order_exports_index')


@login_required
def logs(request, order_export_id):
    if not request.user.can('orders.use'):
        raise PermissionDenied()

    order_export = get_object_or_404(OrderExport, pk=order_export_id,
                                     store__user_id=request.user.id)

    breadcrumbs = [
        {'title': 'Order Exports', 'url': reverse('order_exports_index')},
        {'title': order_export.description, 'url': reverse('order_exports_logs', kwargs={'order_export_id': order_export.id})},
        'Logs'
    ]

    logs = order_export.logs.all()

    return render(request, 'order_exports/logs.html', {
        'logs': logs,
        'page': "order_exports",
        'breadcrumbs': breadcrumbs
    })


@login_required
def generated(request, order_export_id, code):
    if request.user.is_vendor:
        order_export = get_object_or_404(OrderExport, pk=order_export_id,
                                         vendor_user__user_id=request.user.id)
    else:
        if not request.user.can('orders.use'):
            raise PermissionDenied()

        order_export = get_object_or_404(OrderExport, pk=order_export_id,
                                         store__user_id=request.user.id)

    breadcrumbs = [
        {'title': 'Order Exports', 'url': reverse('order_exports_index')},
        {'title': order_export.description, 'url': reverse('order_exports_generated', kwargs={
            'order_export_id': order_export.id, 'code': code
        })},
        'Generated Page'
    ]

    page = int(request.GET.get('page') or '1')
    order_export = OrderExport.objects.get(pk=order_export_id)
    api = ShopifyOrderExportAPI(order_export, code=code)

    info = api.get_query_info()
    data = api.get_data(page=page)

    return render(request, 'order_exports/generated.html', {
        'info': info,
        'data': data,
        'page': "order_exports",
        'breadcrumbs': breadcrumbs,
        'current_page': page,
        'order_export_id': order_export_id,
        'code': code
    })


@login_required
def delete_vendor(request, vendor_id):
    vendor_user = get_object_or_404(OrderExportVendor, pk=vendor_id,
                                    owner_id=request.user.id)
    vendor_user.user.delete()
    vendor_user.delete()

    return JsonResponse({'success': True})


@login_required
def fulfill_order(request, order_export_id, code, order_id, line_item_id):
    if request.user.is_vendor:
        order_export = get_object_or_404(OrderExport, pk=order_export_id,
                                         vendor_user__user_id=request.user.id)
    else:
        if not request.user.can('orders.use'):
            raise PermissionDenied()

        order_export = get_object_or_404(OrderExport, pk=order_export_id,
                                         store__user_id=request.user.id)

    api = ShopifyOrderExportAPI(order_export, code=code)
    tracking_number = request.POST.get('tracking_number')
    fulfillment_id = request.POST.get('fulfillment_id')
    success = api.fulfill(order_id, tracking_number, line_item_id, fulfillment_id)

    return JsonResponse({'success': success})


def vendor_autocomplete(request):
    vendor = request.GET.get('query', '').strip()
    if not vendor:
        vendor = request.GET.get('term', '').strip()

    if not vendor:
        return JsonResponse({'query': vendor, 'suggestions': []}, safe=False)

    vendors = OrderExportFilter.objects.filter(
        vendor__icontains=vendor,
        orderexport__store__user=request.user.pk
    ).values_list('vendor', flat=True)
    return JsonResponse({'query': vendor, 'suggestions': [{'value': i, 'data': i} for i in vendors]}, safe=False)


def create_vendor_user(request):
    vendor_user_id = request.POST.get('vendor_user')

    if vendor_user_id:
        user = User.objects.get(pk=vendor_user_id)
        vendors = user.vendors.filter(owner=request.user)

        if not vendors.exists():
            vendor_user = OrderExportVendor()
            vendor_user.user = user
            vendor_user.owner = request.user

            vendor_user.save()
            vendor_user_id = vendor_user.id
        else:
            vendor_user_id = vendors.first().id

    return vendor_user_id
