from django.core.management.base import BaseCommand
from leadgalaxy.models import *
from django.utils import timezone


class Command(BaseCommand):

    help = 'Delete Users on FreePlan for more then 30 days'

    def handle(self, *args, **kwargs):
        group_plan_change_logs = GroupPlanChangeLog.objects.all()

        for change_log in group_plan_change_logs:
            time_delta = timezone.now() - change_log.updated_at
            if change_log.plan.is_free \
                    and time_delta.days >= 30:
                self.stdout.write('User: "{}" is on "{}" Plan Since "{}" '.format(
                    change_log.user_profile.user.username,
                    change_log.plan.title,
                    time_delta.days
                ))
