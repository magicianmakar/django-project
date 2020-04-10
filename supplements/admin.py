# -*- coding: utf-8 -*-
from django.contrib import admin

from .models import (
    AuthorizeNetCustomer,
    LabelComment,
    LabelSize,
    MockupType,
    Payout,
    PLSOrder,
    PLSOrderLine,
    PLSupplement,
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


@admin.register(PLSOrder)
class PLSOrderAdmin(admin.ModelAdmin):
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
