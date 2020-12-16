from django.contrib import admin
from adminsortable2.admin import SortableInlineAdminMixin

from addons_core.admin import FormWithRequestMixin
from .forms import StepForm
from .models import Goal, UserGoalRelationship, GoalStepRelationship, Step, StepExtraAction


class GoalStepRelationshipInline(SortableInlineAdminMixin, admin.TabularInline):
    model = Goal.steps.through
    verbose_name = "step"
    extra = 1


@admin.register(UserGoalRelationship)
class UserGoalRelationshipAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'goal', 'viewed')
    list_filter = ('viewed',)
    raw_id_fields = ('user', 'goal')


@admin.register(GoalStepRelationship)
class GoalStepRelationshipAdmin(admin.ModelAdmin):
    list_display = ('id', 'goal', 'step', 'step_number')
    raw_id_fields = ('goal', 'step')


@admin.register(Goal)
class GoalAdmin(admin.ModelAdmin):
    list_display = ('id', 'goal_number', 'title', 'description', 'tip')
    search_fields = ('id', 'title', 'description')
    inlines = (GoalStepRelationshipInline,)
    exclude = ('users',)


@admin.register(Step)
class StepAdmin(FormWithRequestMixin, admin.ModelAdmin):
    list_display = (
        'id',
        'title',
        'description',
        'slug',
        'show_me_how_url',
        'action_url',
        'action_title',
        'icon_src',
    )
    search_fields = ('slug',)
    exclude = ('users',)
    prepopulated_fields = {"slug": ("title",)}
    form = StepForm


@admin.register(StepExtraAction)
class StepExtraActionAdmin(admin.ModelAdmin):
    list_display = ('id', 'step', 'action_url', 'action_title', 'icon_src')
    raw_id_fields = ('step',)
