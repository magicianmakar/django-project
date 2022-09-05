from django.contrib import admin
from django.urls import reverse

from .models import MasterProduct, MasterProductSupplier, ProductTemplate

USER_SEARCH_FIELDS = ('user__id', 'user__username', 'user__email')


@admin.register(MasterProduct)
class MasterProductAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'user', 'created_at', 'updated_at')
    raw_id_fields = ('user',)
    ordering = ('-updated_at',)
    search_fields = ('extension_data',)

    def view_on_site(self, obj):
        return reverse('product_view', kwargs={'pid': obj.id})


@admin.register(MasterProductSupplier)
class MasterProductSupplierAdmin(admin.ModelAdmin):
    list_display = ('id', 'product', 'supplier_name', 'supplier_url', 'created_at', 'updated_at', )
    list_filter = ('is_default', 'created_at', 'updated_at')
    raw_id_fields = ('product', )
    date_hierarchy = 'created_at'


@admin.register(ProductTemplate)
class ProductTemplateAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'type', 'created_at', 'updated_at')
    ordering = ('-created_at',)
    search_fields = ('store_type', 'type')
