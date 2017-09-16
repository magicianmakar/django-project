
from django.contrib import admin

from models import LastSeen


class LastSeenAdmin(admin.ModelAdmin):
    list_display = ('user', 'plan', 'module', 'last_seen')
    list_filter = ('module', 'last_seen', 'user__profile__plan')
    search_fields = ('user__username', 'user__email')

    def plan(self, obj):
        return obj.user.profile.plan.title


admin.site.register(LastSeen, LastSeenAdmin)
