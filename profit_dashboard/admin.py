from django.contrib import admin
from .models import (
    FacebookAccess,
    FacebookAccount,
    FacebookAdCost,
    AliexpressFulfillmentCost,
    OtherCost,
)


admin.site.register(FacebookAccess)
admin.site.register(FacebookAccount)
admin.site.register(FacebookAdCost)
admin.site.register(AliexpressFulfillmentCost)
admin.site.register(OtherCost)
