from django.contrib import admin
from .models import Goal, UserGoalRelationship, GoalStepRelationship, Step, StepExtraAction


class GoalStepRelationshipInline(admin.TabularInline):
    model = Goal.steps.through
    verbose_name = "step"


class UserGoalRelationshipInline(admin.StackedInline):
    model = Goal.users.through
    verbose_name = "user"
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
    inlines = GoalStepRelationshipInline, UserGoalRelationshipInline


@admin.register(Step)
class StepAdmin(admin.ModelAdmin):
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


@admin.register(StepExtraAction)
class StepExtraActionAdmin(admin.ModelAdmin):
    list_display = ('id', 'step', 'action_url', 'action_title', 'icon_src')
    raw_id_fields = ('step',)
