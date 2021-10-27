from django.contrib import admin

from .models import HubspotAccount


@admin.register(HubspotAccount)
class HubspotAccountAdmin(admin.ModelAdmin):
    pass
