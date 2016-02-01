from django.contrib import admin
from .models import *
from django.core.urlresolvers import reverse


@admin.register(GroupPlan)
class GroupPlanAdmin(admin.ModelAdmin):
    exclude = ('default_plan',)
    filter_horizontal = ('permissions',)


@admin.register(UserUpload)
class UserUploadAdmin(admin.ModelAdmin):
    raw_id_fields = ('product',)


@admin.register(ShopifyBoard)
class ShopifyBoardAdmin(admin.ModelAdmin):
    raw_id_fields = ('products',)


@admin.register(ShopifyProduct)
class ShopifyProductAdmin(admin.ModelAdmin):
    raw_id_fields = ('parent_product', 'shopify_export', 'store', 'user')
    list_display = ('__str__', 'store_', 'user', 'created_at', 'updated_at')
    ordering = ('-updated_at',)

    def store_(self, obj):
        return obj.store.title

    def view_on_site(self, obj):
        return reverse('product_view', kwargs={'pid': obj.id})


@admin.register(ShopifyProductExport)
class ShopifyProductExportAdmin(admin.ModelAdmin):
    raw_id_fields = ('store',)

admin.site.register(ShopifyStore)
admin.site.register(AccessToken)
admin.site.register(UserProfile)
admin.site.register(AppPermission)
admin.site.register(PlanRegistration)
admin.site.register(ShopifyOrder)
