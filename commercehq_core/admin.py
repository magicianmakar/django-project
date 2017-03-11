from django.contrib import admin

from .models import (
    CommerceHQStore,
    CommerceHQProduct,
    CommerceHQSupplier,
    CommerceHQBoard,
    CommerceHQOrderTrack,
)


@admin.register(CommerceHQStore)
class CommerceHQStoreAdmin(admin.ModelAdmin):
    raw_id_fields = ('user',)


@admin.register(CommerceHQProduct)
class CommerceHQProductAdmin(admin.ModelAdmin):
    raw_id_fields = ('store', 'user', 'parent_product', 'default_supplier')


@admin.register(CommerceHQSupplier)
class CommerceHQSupplierAdmin(admin.ModelAdmin):
    raw_id_fields = ('store', 'product')


@admin.register(CommerceHQBoard)
class CommerceHQBoardAdmin(admin.ModelAdmin):
    raw_id_fields = ('user', 'products')


@admin.register(CommerceHQOrderTrack)
class CommerceHQOrderTrackAdmin(admin.ModelAdmin):
    raw_id_fields = ('store', 'user')
