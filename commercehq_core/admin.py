from django.contrib import admin

from .models import CommerceHQStore


@admin.register(CommerceHQStore)
class CommerceHQStoreAdmin(admin.ModelAdmin):
    pass
