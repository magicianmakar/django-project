from unittest.mock import patch

from django.db.utils import IntegrityError

from lib.test import BaseTestCase
from leadgalaxy.tests.factories import UserFactory
from .factories import GoalFactory, StepFactory, GoalWithStepsFactory
from ..models import Goal, UserGoalRelationship, GoalStepRelationship


class GoalTestCase(BaseTestCase):
    def setUp(self):
        self.goal = GoalWithStepsFactory()
        self.user = UserFactory()

    def test_can_order_steps_by_step_number(self):
        goal = GoalFactory()
        step2 = StepFactory(slug='step 2')
        goal_step = GoalStepRelationship(goal=goal, step=step2, step_number=2)
        goal_step.save()
        step1 = StepFactory(slug='step 1')
        goal_step = GoalStepRelationship(goal=goal, step=step1, step_number=1)
        goal_step.save()

        goal_steps = GoalStepRelationship.objects.all()
        correct_order = all(goal_steps[i - 1].step_number <= goal_step.step_number
                            for i, goal_step in enumerate(goal_steps) if i > 0)
        self.assertTrue(correct_order)

    def test_goals_are_added_to_new_users(self):
        self.user.profile.plan.goals.add(self.goal)
        goals = list(Goal.objects.all())
        user_goals = list(self.user.goal_set.all())
        self.assertEqual(goals, user_goals)


class UserGoalRelationshipTestCase(BaseTestCase):
    def setUp(self):
        self.user = UserFactory()
        for goal in Goal.objects.all():
            goal.plans.add(self.user.profile.plan)

    def test_returns_number_of_steps_completed_by_user(self):
        goal = GoalFactory()
        user_goal = UserGoalRelationship.objects.create(user=self.user, goal=goal)
        step = StepFactory()
        GoalStepRelationship.objects.create(goal=goal, step=step, step_number=1)
        GoalStepRelationship.objects.create(goal=goal, step=StepFactory(), step_number=2)
        self.user.completed_steps.add(step)
        self.user.completed_steps.add(StepFactory())
        self.assertEqual(user_goal.total_steps_completed, 1)

    @patch('goals.models.UserGoalRelationship.objects.create')
    def test_goals_are_not_added_post_user_save(self, create):
        self.user.username = 'newusername'
        self.user.save()
        self.assertEqual(create.call_count, 0)

    def test_goal_must_be_unique_per_user(self):
        goal = GoalFactory()
        UserGoalRelationship.objects.create(user=self.user, goal=goal)
        with self.assertRaises(IntegrityError):
            UserGoalRelationship.objects.create(user=self.user, goal=goal)
