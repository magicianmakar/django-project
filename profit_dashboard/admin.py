from django.contrib import admin
from .models import (
    FacebookAccess,
    FacebookAccount,
    FacebookInsight,
    ShopifyProfit,
    ShopifyProfitImportedOrder,
    ShopifyProfitImportedOrderTrack,
)


admin.site.register(FacebookAccess)
admin.site.register(FacebookAccount)
admin.site.register(FacebookInsight)
admin.site.register(ShopifyProfit)
admin.site.register(ShopifyProfitImportedOrder)
admin.site.register(ShopifyProfitImportedOrderTrack)
