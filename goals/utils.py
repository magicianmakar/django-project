from django.db.models import Prefetch

from . import step_slugs
from .models import Step


def get_dashboard_user_goals(user):
    user_goals = user.usergoalrelationship_set.all()
    user_goals = user_goals.select_related('user', 'goal')
    user_goals = user_goals.order_by('goal__goal_number')
    user_goals = user_goals.prefetch_related('user__completed_steps')
    queryset = Step.objects.order_by('goalsteprelationship__step_number')
    prefetch = Prefetch('goal__steps', queryset=queryset)
    user_goals = user_goals.prefetch_related(prefetch)

    return user_goals


def update_completed_steps(user):
    """
    Updates a user's list of completed steps by checking if other steps have
    been completed.
    """
    function_map = get_step_check_function_map()
    slugs = function_map.keys()
    steps = Step.objects.filter(slug__in=slugs).exclude(users=user)
    new_completed_steps = []

    for step in steps:
        user_has_done_step = function_map.get(step.slug)
        if user_has_done_step(user):
            new_completed_steps.append(step)

    user.completed_steps.add(*new_completed_steps)


def get_step_check_function_map():
    """
    Returns a map of functions.

    Each function checks whether the user has done a certain step.
    """
    return {
        step_slugs.SAVE_PRODUCT_TO_DROPIFIED: user_saved_a_product,
        step_slugs.ADD_PRODUCT_TO_BOARD: user_has_board_filled}


def user_saved_a_product(user):
    return user.profile.has_product


def user_has_board_filled(user):
    return user.profile.has_product_on_board
