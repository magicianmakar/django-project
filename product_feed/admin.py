from django.contrib import admin

from .models import FeedStatus


@admin.register(FeedStatus)
class FeedStatusAdmin(admin.ModelAdmin):
    list_display = ('store', 'status', 'created_at', 'updated_at')
    exclude = []
