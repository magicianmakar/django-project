import json
from datetime import datetime

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.core.urlresolvers import reverse
from django.contrib import messages

from order_exports.api import ShopifyOrderExportAPI
from order_exports.forms import OrderExportForm
from order_exports.models import OrderExport, OrderExportFilter, fix_fields, \
    ORDER_FIELD_CHOICES, ORDER_LINE_FIELD_CHOICES, ORDER_STATUS, \
    ORDER_FULFILLMENT_STATUS, ORDER_FINANCIAL_STATUS, ORDER_SHIPPING_ADDRESS_CHOICES, \
    DEFAULT_FIELDS, DEFAULT_FIELDS_CHOICES


@login_required
def index(request):
    saved = 'saved' in request.GET
    order_exports = OrderExport.objects.filter(store__user=request.user.pk)
    
    return render(request, 'order_exports/index.html', {
        'order_exports': order_exports, 'page': "order_exports",
        'saved': saved
    })


@login_required
def add(request):
    form = None
    
    fields = DEFAULT_FIELDS
    fields_choices = DEFAULT_FIELDS_CHOICES
    shipping_address = []
    shipping_address_choices = []
    line_fields = []
    line_fields_choices = []

    if request.method == 'POST':
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
            filters = OrderExportFilter.objects.create(
                vendor=request.POST.get('vendor'),
                status=request.POST.get('status'),
                fulfillment_status=request.POST.get('fulfillment_status'),
                financial_status=request.POST.get('financial_status')
            )

            order_export = OrderExport.objects.create(
                store_id=request.POST.get('store'),
                schedule=request.POST.get('schedule'),
                receiver=request.POST.get('receiver'),
                description=request.POST.get('description'),
                fields=fields,
                shipping_address=shipping_address,
                line_fields=line_fields,
                filters=filters,
            )

            order_export.save()

            messages.success(request, 'Created order exports successfuly')
            return redirect(reverse('order_exports_index'))

    return render(request, 'order_exports/add.html', {
        'form': form, 'page': "order_exports", 'order_status': ORDER_STATUS, 
        'order_fulfillment_status': ORDER_FULFILLMENT_STATUS, 
        'order_financial_status': ORDER_FINANCIAL_STATUS, 
        'order_fields': ORDER_FIELD_CHOICES, 
        'order_line_fields': ORDER_LINE_FIELD_CHOICES,
        'order_shipping_address': ORDER_SHIPPING_ADDRESS_CHOICES, 
        'selected_fields': fields, 'fields_choices': fields_choices, 
        'selected_shipping_address': shipping_address, 'shipping_address_choices': shipping_address_choices,
        'selected_line_fields': line_fields, 'line_fields_choices': line_fields_choices,
    })


@login_required
def edit(request, order_export_id):
    order_export = get_object_or_404(OrderExport, pk=order_export_id, 
        store__user_id=request.user.id)
    
    form = None

    fields = order_export.fields_data
    fields_choices = order_export.fields_choices
    shipping_address = order_export.shipping_address_data
    shipping_address_choices = order_export.shipping_address_choices
    line_fields = order_export.line_fields_data
    line_fields_choices = order_export.line_fields_choices

    if request.method == 'POST':
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
            order_export.store_id = request.POST.get('store')
            order_export.schedule = request.POST.get('schedule')
            order_export.receiver = request.POST.get('receiver')
            order_export.description = request.POST.get('description')

            for field_name in ['fields', 'line_fields', 'shipping_address']:
                fields_list = json.loads(request.POST.get(field_name))
                fields = []
                for field in fields_list:
                    fields.append(field.replace(field_name+'_', ''))
                setattr(order_export, field_name, json.dumps(fields))

            filters = OrderExportFilter.objects.create(
                vendor=request.POST.get('vendor'),
                status=request.POST.get('status'),
                fulfillment_status=request.POST.get('fulfillment_status'),
                financial_status=request.POST.get('financial_status')
            )

            order_export.filters.delete()
            order_export.filters = filters
            order_export.save()

            messages.success(request, 'Edited order exports successfuly')
            return redirect(reverse('order_exports_index'))

    return render(request, 'order_exports/edit.html', {'order_export': order_export, 
        'form': form, 'page': "order_exports", 'order_status': ORDER_STATUS, 
        'order_fulfillment_status': ORDER_FULFILLMENT_STATUS, 
        'order_financial_status': ORDER_FINANCIAL_STATUS, 
        'order_fields': ORDER_FIELD_CHOICES, 
        'order_line_fields': ORDER_LINE_FIELD_CHOICES,
        'order_shipping_address': ORDER_SHIPPING_ADDRESS_CHOICES, 
        'selected_fields': fields, 'fields_choices': fields_choices, 
        'selected_shipping_address': shipping_address, 'shipping_address_choices': shipping_address_choices,
        'selected_line_fields': line_fields, 'line_fields_choices': line_fields_choices,
    })


@login_required
def delete(request, order_export_id):
    order_export = get_object_or_404(OrderExport, pk=order_export_id, 
        store__user_id=request.user.id)
    order_export.delete()

    return redirect('order_exports_index')
