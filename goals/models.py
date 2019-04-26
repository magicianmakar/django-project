# -*- coding: utf-8 -*-
from __future__ import unicode_literals

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
    user = models.ForeignKey(settings.AUTH_USER_MODEL)
    goal = models.ForeignKey('goals.Goal')

    class Meta:
        unique_together = 'user', 'goal'

    @cached_property
    def total_steps_completed(self):
        """
        Returns the count of the steps completed by the user that also belongs
        to this goal.
        """
        return len(set(self.user.completed_steps.all()) & set(self.goal.steps.all()))


class GoalStepRelationship(models.Model):
    goal = models.ForeignKey('goals.Goal')
    step = models.ForeignKey('goals.Step')
    step_number = models.PositiveIntegerField()

    class Meta:
        verbose_name = 'goal step'
        unique_together = 'goal', 'step_number'


class Step(models.Model):
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
