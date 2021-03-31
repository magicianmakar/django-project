from shopified_core.management import DropifiedBaseCommand
from django.contrib.auth.models import User
from churnzero_core.utils import set_churnzero_account

#  55472/119912


class Command(DropifiedBaseCommand):
    def start_command(self, *args, **options):
        users = User.objects.filter(profile__subuser_parent__isnull=True)
        self.progress_total(users.count())
        for user in users:
            self.progress_update()

            try:
                if user.profile.plan and (user.profile.plan.is_stripe() or user.profile.plan.is_shopify()):
                    set_churnzero_account(user)

            except Exception:
                self.write(f'Error for {user.email}')
