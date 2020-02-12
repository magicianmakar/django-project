# -*- coding: utf-8 -*-
from django.contrib import admin

from .models import Order, OrderLine, Payout, Product, ProductImage


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'title',
        'description',
        'category',
        'tags',
        'shipstation_sku',
        'cost_price',
        'product_type',
    )


@admin.register(ProductImage)
class ProductImageAdmin(admin.ModelAdmin):
    list_display = ('id', 'position', 'image_url', 'product')
    raw_id_fields = ('product',)


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'store_type',
        'store_id',
        'store_order_id',
        'order_number',
        'stripe_transaction_id',
        'shipstation_key',
        'amount',
        'status',
        'user',
        'payout',
        'created_at',
        'payment_date',
    )
    list_filter = ('created_at', 'payment_date')
    raw_id_fields = ('user', 'payout')
    date_hierarchy = 'created_at'


@admin.register(OrderLine)
class OrderLineAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'store_type',
        'store_id',
        'store_order_id',
        'line_id',
        'sku',
        'shipstation_key',
        'order',
        'created_at',
    )
    list_filter = ('created_at',)
    raw_id_fields = ('order',)
    date_hierarchy = 'created_at'


@admin.register(Payout)
class PayoutAdmin(admin.ModelAdmin):
    list_display = ('id', 'reference_number', 'status', 'created_at')
    list_filter = ('created_at',)
    date_hierarchy = 'created_at'
