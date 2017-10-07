
from django.contrib import admin

from models import LastSeen


class PlanListFilter(admin.SimpleListFilter):
    title = 'Plan'
    parameter_name = 'user__profile__plan'

    def lookups(self, request, model_admin):
        choices = []
        choices_count = {}
        qs = model_admin.get_queryset(request)
        for k in request.GET.keys():
            if k != 'q':
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
