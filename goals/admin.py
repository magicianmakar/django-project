from django.contrib import admin
from .models import Goal, Step, StepExtraAction


class GoalStepRelationshipInline(admin.TabularInline):
    model = Goal.steps.through
    verbose_name = "step"


class UserGoalRelationshipInline(admin.StackedInline):
    model = Goal.users.through
    verbose_name = "user"
    extra = 1


@admin.register(Goal)
class GoalAdmin(admin.ModelAdmin):
    list_display = 'title', 'description'
    inlines = GoalStepRelationshipInline, UserGoalRelationshipInline


@admin.register(Step)
class StepAdmin(admin.ModelAdmin):
    list_display = 'slug',


@admin.register(StepExtraAction)
class StepExtraActionAdmin(admin.ModelAdmin):
    list_display = 'action_title',
