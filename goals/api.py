from django.views.generic import View

from shopified_core.mixins import ApiResponseMixin
from .models import Step
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
