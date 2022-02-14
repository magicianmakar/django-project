from django.contrib import admin

from .models import LastSeen, UserIpRecord, BrowserUserAgent


class PlanListFilter(admin.SimpleListFilter):
    title = 'Plan'
    parameter_name = 'user__profile__plan'

    def lookups(self, request, model_admin):
        choices = []
        choices_count = {}
        qs = model_admin.get_queryset(request)
        for k in list(request.GET.keys()):
            if len(k) > 1:
                qs = qs.filter(**{k: request.GET[k]})

        for i in qs.values_list('user__profile__plan_id', 'user__profile__plan__title'):
            if i not in choices:
                choices.append(i)
                choices_count[i[1]] = 1
            else:
                choices_count[i[1]] = choices_count[i[1]] + 1

        for i, val in enumerate(choices):
            choices[i] = (val[0], '{} - {}'.format(choices_count[val[1]], val[1]))

        if not len(choices):
            choices = [(None, 'All')]

        return choices

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(user__profile__plan_id=self.value())


class LastSeenAdmin(admin.ModelAdmin):
    list_display = ('user', 'plan', 'module', 'last_seen')
    list_filter = ('module', 'last_seen', PlanListFilter)
    search_fields = ('user__username', 'user__email')
    select_related = ('user__profile__plan')

    def plan(self, obj):
        return obj.user.profile.plan.title


admin.site.register(LastSeen, LastSeenAdmin)


@admin.register(BrowserUserAgent)
class BrowserUserAgentAdmin(admin.ModelAdmin):
    list_display = ('id', 'description', 'is_bot', 'created_at')
    list_filter = ('created_at',)
    date_hierarchy = 'created_at'


@admin.register(UserIpRecord)
class UserIpRecordAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'user',
        'browser',
        'ip',
        'country',
        'city',
        'created_at',
        'last_seen_at',
    )
    list_filter = ('created_at', 'last_seen_at')
    raw_id_fields = ('user', 'browser', 'session')
    date_hierarchy = 'last_seen_at'
