from django.db import models
from django.conf import settings
from django.utils.functional import cached_property


class Goal(models.Model):
    users = models.ManyToManyField(settings.AUTH_USER_MODEL, blank=True, through='UserGoalRelationship')
    steps = models.ManyToManyField('goals.Step', blank=True, through='GoalStepRelationship')
    goal_number = models.PositiveIntegerField(unique=True)
    title = models.CharField(max_length=512, blank=True, default='')
    description = models.CharField(max_length=512, blank=True, default='')
    tip = models.CharField(max_length=512, blank=True, default='')

    def __str__(self):
        return self.title


class UserGoalRelationship(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    goal = models.ForeignKey('goals.Goal', on_delete=models.CASCADE)
    viewed = models.BooleanField(default=False)

    class Meta:
        unique_together = 'user', 'goal'

    @cached_property
    def total_steps_completed(self):
        """
        Returns the count of the steps completed by the user that also belongs
        to this goal.
        """
        step_ids = [s.id for s in self.goal.steps.all()]
        return self.user.completed_steps.filter(id__in=step_ids).count()


class GoalStepRelationship(models.Model):
    goal = models.ForeignKey('goals.Goal', on_delete=models.CASCADE)
    step = models.ForeignKey('goals.Step', on_delete=models.CASCADE)
    step_number = models.PositiveIntegerField()

    class Meta:
        verbose_name = 'goal step'
        unique_together = 'goal', 'step_number'


class ActionMixin:
    """
    Adding it till Step contains action url.
    TODO: Remove when action is taken out of Step completely.
    """
    @property
    def is_external(self):
        return ('dropified' not in self.action_url
                or not self.action_url.startswith("http"))


class Step(models.Model, ActionMixin):
    users = models.ManyToManyField(settings.AUTH_USER_MODEL, blank=True, related_name='completed_steps')
    title = models.CharField(max_length=512, blank=True, default='')
    description = models.CharField(max_length=512, blank=True, default='')
    slug = models.SlugField(max_length=30, unique=True)
    show_me_how_url = models.URLField(blank=True, default='')
    action_url = models.URLField(blank=True, default='')
    action_title = models.CharField(max_length=100, blank=True, default='')
    icon_src = models.CharField(max_length=200, blank=True, default='')

    def __str__(self):
        return self.slug


class StepExtraAction(models.Model, ActionMixin):
    """
    TODO: Eventually we should remove the following fields from Step model:
        action_url = models.URLField(blank=True, default='')
        action_title = models.CharField(max_length=100, blank=True, default='')
        icon_src = models.CharField(max_length=200, blank=True, default='')

    Then we can solely use this model for managing actions.
    """
    step = models.ForeignKey(Step,
                             on_delete=models.CASCADE,
                             related_name='extra_actions')
    action_url = models.URLField(blank=True, default='')
    action_title = models.CharField(max_length=100, blank=True, default='')
    icon_src = models.CharField(max_length=200, blank=True, default='')
