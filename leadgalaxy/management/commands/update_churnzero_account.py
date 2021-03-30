from shopified_core.management import DropifiedBaseCommand
from django.contrib.auth.models import User
from churnzero_core.utils import set_churnzero_account


class Command(DropifiedBaseCommand):
    def start_command(self, *args, **options):
        for user in User.objects.filter(profile__subuser_parent__isnull=True):
            if user.profile.plan:
                if user.profile.plan.is_stripe() or user.profile.plan.is_shopify():
                    self.write(f"Updating ChurnZero account for {user.username}")
                    try:
                        set_churnzero_account(user)
                    except Exception:
                        self.write("Update failed")
                    else:
                        self.write("Update successful")
