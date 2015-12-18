from django.contrib import admin
from .models import *

class GroupPlanAdmin(admin.ModelAdmin):
    exclude = ('default_plan',)
    filter_horizontal = ('permissions',)

class UserUploadAdmin(admin.ModelAdmin):
    raw_id_fields = ('product',)

class ShopifyBoardAdmin(admin.ModelAdmin):
    raw_id_fields = ('products',)

class ShopifyProductExportAdmin(admin.ModelAdmin):
    raw_id_fields = ('store',)

admin.site.register(ShopifyStore)
admin.site.register(AccessToken)
admin.site.register(ShopifyProduct)
admin.site.register(ShopifyBoard, ShopifyBoardAdmin)
admin.site.register(GroupPlan, GroupPlanAdmin)
admin.site.register(UserProfile)
admin.site.register(UserUpload, UserUploadAdmin)
admin.site.register(AppPermission)
admin.site.register(ShopifyProductExport, ShopifyProductExportAdmin)
