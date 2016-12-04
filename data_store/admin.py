from django.contrib import admin
from .models import *


@admin.register(DataStore)
class GroupPlanAdmin(admin.ModelAdmin):
    list_display = ('key',)
    readonly_fields = ('key',)
