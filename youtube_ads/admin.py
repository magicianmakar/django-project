# -*- coding: utf-8 -*-
from django.contrib import admin

from .models import VideosList


@admin.register(VideosList)
class VideosListAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'title', 'videos', 'created_at', 'updated_at')
    list_filter = ('created_at', 'updated_at')
    raw_id_fields = ('user',)
    date_hierarchy = 'created_at'
