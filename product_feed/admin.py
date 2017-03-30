from django.contrib import admin

from .models import FeedStatus


@admin.register(FeedStatus)
class FeedStatusAdmin(admin.ModelAdmin):
    list_display = ('store', 'status', 'generation_time', 'fb_access_at', 'updated_at')
    raw_id_fields = ('store',)
    list_filter = ('status',)
    search_fields = ('store__id', 'store__title', 'store__user__id', 'store__user__email')
