from unittest.mock import patch

from django.db.utils import IntegrityError

from lib.test import BaseTestCase
from leadgalaxy.tests.factories import UserFactory
from .factories import GoalFactory, StepFactory
from ..models import Goal, UserGoalRelationship, GoalStepRelationship


class GoalTestCase(BaseTestCase):
    def test_can_order_steps_by_step_number(self):
        goal = GoalFactory()
        step2 = StepFactory(slug='step 2')
        goal_step = GoalStepRelationship(goal=goal, step=step2, step_number=2)
        goal_step.save()
        step1 = StepFactory(slug='step 1')
        goal_step = GoalStepRelationship(goal=goal, step=step1, step_number=1)
        goal_step.save()
        steps = goal.steps.order_by('goalsteprelationship__step_number')
        self.assertEqual([step1, step2], list(steps))

    def test_goals_are_added_to_new_users(self):
        GoalFactory()
        user = UserFactory()
        goals = list(Goal.objects.all())
        user_goals = list(user.goal_set.all())
        self.assertEqual(goals, user_goals)


class UserGoalRelationshipTestCase(BaseTestCase):
    def test_returns_number_of_steps_completed_by_user(self):
        user = UserFactory()
        goal = GoalFactory()
        user_goal = UserGoalRelationship.objects.create(user=user, goal=goal)
        step = StepFactory()
        GoalStepRelationship.objects.create(goal=goal, step=step, step_number=1)
        GoalStepRelationship.objects.create(goal=goal, step=StepFactory(), step_number=2)
        user.completed_steps.add(step)
        user.completed_steps.add(StepFactory())
        self.assertEqual(user_goal.total_steps_completed, 1)

    @patch('goals.models.UserGoalRelationship.objects.create')
    def test_goals_are_not_added_post_user_save(self, create):
        user = UserFactory()
        user.username = 'newusername'
        user.save()
        self.assertEqual(create.call_count, Goal.objects.count())

    def test_goal_must_be_unique_per_user(self):
        user = UserFactory()
        goal = GoalFactory()
        UserGoalRelationship.objects.create(user=user, goal=goal)
        with self.assertRaises(IntegrityError):
            UserGoalRelationship.objects.create(user=user, goal=goal)


class GoalStepRelationshipTestCase(BaseTestCase):
    def test_goal_step_number_must_be_unique_per_goal(self):
        goal = GoalFactory()
        step = StepFactory()
        goal_step = GoalStepRelationship(goal=goal, step=step, step_number=1)
        goal_step.save()
        goal_step = GoalStepRelationship(goal=goal, step=step, step_number=1)
        self.assertRaises(IntegrityError, lambda: goal_step.save())
