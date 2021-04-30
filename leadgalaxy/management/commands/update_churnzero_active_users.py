from shopified_core.management import DropifiedBaseCommand
from django.contrib.auth.models import User
from churnzero_core.utils import post_churnzero_actions, SetAccountActionBuilder

#  55472/119912


class Command(DropifiedBaseCommand):
    def start_command(self, *args, **options):
        users = User.objects.filter(profile__subuser_parent__isnull=True)
        self.progress_total(users.count())
        for user in users:
            self.progress_update()
            try:
                if user.profile.plan and (user.profile.plan.is_stripe() or user.profile.plan.is_shopify()):
                    builder = SetAccountActionBuilder(user)
                    action = builder.get_action()
                    action['attr_IsActive'] = self.is_user_plan_free(user.models_user)
                    post_churnzero_actions(actions=[action])
            except Exception:
                self.write(f'Error for {user.email}')

    def is_user_plan_free(self, models_user):
        plan = models_user.profile.plan

        return plan and not (plan.free_plan or plan.is_free or plan.is_active_free)
