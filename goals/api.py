from django.views.generic import View

from shopified_core.mixins import ApiResponseMixin
from .models import Step, UserGoalRelationship
from . import step_slugs


class GoalsApi(ApiResponseMixin, View):
    def post_extension_is_installed(self, request, user, data):
        slug = step_slugs.INSTALL_CHROME_EXTENSION
        step = Step.objects.filter(slug=slug).exclude(users=user).first()

        if step:
            user.completed_steps.add(step)
            goals = step.goal_set.values_list('pk', flat=True)
            return self.api_success({'added': True, 'slug': slug, 'goals': list(goals)})

        return self.api_success({'added': False})

    def post_step_is_completed(self, request, user, data):
        goal_id = data['goal_id']
        slug = data['step_slug']
        step = Step.objects.filter(slug=slug).exclude(users=user).first()

        if step:
            user.completed_steps.add(step)
            completed_steps = user.completed_steps.filter(goal=goal_id).count()
            return self.api_success({'added': True,
                                     'slug': slug,
                                     'steps': completed_steps})

        return self.api_success({'added': False})

    def post_goal_is_viewed(self, request, user, data):
        user_goal_id = data['user_goal_id']
        try:
            user_goal = UserGoalRelationship.objects.get(id=user_goal_id)
        except UserGoalRelationship.DoesNotExist:
            return self.api_error('Not found', status=404)

        if user_goal.viewed:
            return self.api_success()

        if user_goal.total_steps_completed == user_goal.goal.steps.count():
            user_goal.viewed = True
            user_goal.save()

        return self.api_success()
