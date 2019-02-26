from django.contrib import admin
from .models import DataStore


@admin.register(DataStore)
class GroupPlanAdmin(admin.ModelAdmin):
    list_display = ('key',)
    readonly_fields = ('key',)
