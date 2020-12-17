from django.dispatch import receiver
from django.db.models.signals import m2m_changed
from django.contrib.auth.models import User
from goals.models import Goal, UserGoalRelationship


@receiver(m2m_changed, sender=Goal.plans.through)
def add_goals_to_user_with_plan(sender, instance, pk_set, action, reverse, **kwargs):
    if reverse:
        return True

    if action == 'post_add':
        users = User.objects.filter(profile__plan=instance)
        for goal in Goal.objects.filter(id__in=pk_set):
            for user in users:
                UserGoalRelationship.objects.get_or_create(user=user, goal=goal)

    if action == 'post_remove':
        users = User.objects.filter(profile__plan=instance)
        for user in users:
            UserGoalRelationship.objects.filter(user=user, goal_id__in=pk_set).delete()
