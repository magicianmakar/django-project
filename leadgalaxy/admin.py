from django.contrib import admin
from .models import *

admin.site.register(ShopifyStore)
admin.site.register(AccessToken)
admin.site.register(ShopifyProduct)
admin.site.register(ShopifyBoard)
admin.site.register(GroupPlan)
admin.site.register(UserProfile)
admin.site.register(UserUpload)
