# -*- coding: utf-8 -*-
from django.contrib import admin

from .models import SureDoneAccount


@admin.register(SureDoneAccount)
class SureDoneAccountAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'list_index',
        'currency_format',
        'user',
        'title',
        'email',
        'password',
        'sd_id',
        'options_config_data',
        'api_username',
        'api_token',
        'is_active',
        'store_hash',
        'created_at',
        'updated_at',
    )
    list_filter = ('is_active', 'created_at', 'updated_at')
    raw_id_fields = ('user',)
    date_hierarchy = 'created_at'
