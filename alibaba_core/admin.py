from django.contrib import admin

from .models import AlibabaAccount, AlibabaOrder, AlibabaOrderItem

admin.site.register([AlibabaAccount, AlibabaOrder, AlibabaOrderItem])
