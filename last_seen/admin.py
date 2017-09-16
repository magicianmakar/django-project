
from django.contrib import admin

from models import LastSeen


class LastSeenAdmin(admin.ModelAdmin):
    list_display = ('user', 'module', 'last_seen')
    list_filter = ('module', 'last_seen')
    search_fields = ('user__username', 'user__email')


admin.site.register(LastSeen, LastSeenAdmin)
