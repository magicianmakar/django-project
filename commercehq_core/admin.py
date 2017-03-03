from django.contrib import admin

from .models import *


@admin.register(CommerceHQStore)
class CommerceHQStoreAdmin(admin.ModelAdmin):
    pass


@admin.register(CommerceHQProduct)
class CommerceHQProductAdmin(admin.ModelAdmin):
    pass


@admin.register(CommerceHQBoard)
class CommerceHQBoardAdmin(admin.ModelAdmin):
    pass
