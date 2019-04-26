from leadgalaxy.tests.factories import (
    UserFactory,
    ShopifyProductFactory,
    ShopifyStoreFactory,
    ShopifyBoardFactory,
)
from lib.test import BaseTestCase
from ..utils import update_completed_steps, get_dashboard_user_goals
from ..models import Step, Goal, UserGoalRelationship, GoalStepRelationship
from .. import step_slugs
from .factories import GoalFactory, StepFactory


class UpdateCompletedStepsTestCase(BaseTestCase):
    def test_must_not_have_completed_steps(self):
        user = UserFactory()
        update_completed_steps(user)
        self.assertFalse(user.completed_steps.exists())

    def test_must_not_add_save_a_product_step_if_step_does_not_exist(self):
        user = UserFactory()
        slug = step_slugs.SAVE_PRODUCT_TO_DROPIFIED
        Step.objects.filter(slug=slug).delete()
        update_completed_steps(user)
        self.assertFalse(user.completed_steps.filter(slug=slug).exists())

    def test_must_not_add_save_a_product_step_if_user_has_not_saved_a_product(self):
        user = UserFactory()
        update_completed_steps(user)
        self.assertFalse(user.completed_steps.filter(slug=step_slugs.SAVE_PRODUCT_TO_DROPIFIED).exists())

    def test_must_add_save_a_product_step_to_user_if_user_has_saved_a_product(self):
        user = UserFactory()
        ShopifyProductFactory(user=user)
        update_completed_steps(user)
        self.assertTrue(user.completed_steps.filter(slug=step_slugs.SAVE_PRODUCT_TO_DROPIFIED).exists())

    def test_must_not_add_board_filled_step_if_step_does_not_exist(self):
        user = UserFactory()
        slug = step_slugs.ADD_PRODUCT_TO_BOARD
        Step.objects.filter(slug=slug).delete()
        update_completed_steps(user)
        self.assertFalse(user.completed_steps.filter(slug=slug).exists())

    def test_must_not_add_board_filled_step_if_user_has_not_added_product_to_a_board(self):
        user = UserFactory()
        update_completed_steps(user)
        self.assertFalse(user.completed_steps.filter(slug=step_slugs.ADD_PRODUCT_TO_BOARD).exists())

    def test_must_add_board_filled_step_to_user_if_user_has_added_product_to_a_board(self):
        user = UserFactory()
        store = ShopifyStoreFactory(user=user)
        product = ShopifyProductFactory(user=user, store=store)
        board = ShopifyBoardFactory(user=user)
        board.products.add(product)
        update_completed_steps(user)
        self.assertTrue(user.completed_steps.filter(slug=step_slugs.ADD_PRODUCT_TO_BOARD).exists())


class GetDashboardUserGoalsTestCase(BaseTestCase):
    def setUp(self):
        Goal.objects.all().delete()
        Step.objects.all().delete()
        user = self.user = UserFactory()
        goal1 = GoalFactory()
        goal2 = GoalFactory()
        goal3 = GoalFactory()
        UserGoalRelationship.objects.create(user=user, goal=goal1)
        UserGoalRelationship.objects.create(user=user, goal=goal2)
        UserGoalRelationship.objects.create(user=user, goal=goal3)
        GoalStepRelationship.objects.create(goal=goal1, step=StepFactory(), step_number=2)
        GoalStepRelationship.objects.create(goal=goal1, step=StepFactory(), step_number=1)
        GoalStepRelationship.objects.create(goal=goal2, step=StepFactory(), step_number=2)
        GoalStepRelationship.objects.create(goal=goal2, step=StepFactory(), step_number=1)
        GoalStepRelationship.objects.create(goal=goal3, step=StepFactory(), step_number=2)
        GoalStepRelationship.objects.create(goal=goal3, step=StepFactory(), step_number=1)

    def test_must_only_query_three_times(self):
        with self.assertNumQueries(3):
            for user_goal in get_dashboard_user_goals(self.user):
                user_goal.user.id
                user_goal.goal.id
                user_goal.total_steps_completed
                user_goal.goal.steps.count()
                for step in user_goal.goal.steps.all():
                    step in user_goal.user.completed_steps.all()

    def test_must_order_steps_by_ascending_step_number(self):
        for user_goal in get_dashboard_user_goals(self.user):
            goal = Goal.objects.get(id=user_goal.goal.id)
            ordered_steps = list(goal.steps.order_by('goalsteprelationship__step_number'))
            steps = list(user_goal.goal.steps.all())
            self.assertEqual(steps, ordered_steps)
