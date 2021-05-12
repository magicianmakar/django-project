from django.contrib import admin

from .models import AlibabaAccount, AlibabaOrder, AlibabaOrderItem

admin.site.register([AlibabaOrder, AlibabaOrderItem])


@admin.register(AlibabaAccount)
class AlibabaAccountAdmin(admin.ModelAdmin):
    list_display = ('get_user_email', 'alibaba_user_id', 'access_token', 'expired_at')
    search_fields = ('user__id', 'user__email', 'alibaba_user_id', 'access_token', 'ecology_token')
    raw_id_fields = ('user',)

    def get_user_email(self, obj):
        return obj.user.email
