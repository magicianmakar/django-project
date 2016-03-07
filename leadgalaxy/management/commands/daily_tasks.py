from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth.models import User
from django.utils import timezone

from leadgalaxy.models import *
from leadgalaxy import utils

class Command(BaseCommand):
    def add_arguments(self, parser):
        pass

    def handle(self, *args, **options):
        # Archive seen changes
        self.stdout.write(self.style.HTTP_INFO('* Archive seen alerts'))
        AliexpressProductChange.objects.filter(seen=True, hidden=False).update(hidden=True)

        # Expired plans
        self.stdout.write(self.style.HTTP_INFO('* Change plan of expired profiles'))
        for profile in UserProfile.objects.filter(plan_expire_at__lte=timezone.now()):
            if profile.plan_after_expire:
                print 'Changing:', profile
                self.profile_changed(profile, profile.plan, profile.plan_after_expire)

                profile.plan = profile.plan_after_expire
                profile.plan_after_expire = None
                profile.plan_expire_at = None
                profile.save()

    def profile_changed(self, profile, expired_plan, new_plan):
        data = {
            'profile': profile,
            'expired_plan': expired_plan,
            'new_plan': new_plan
        }

        utils.send_email_from_template(tpl='expire_plan_change.html',
                                       subject='[Shopified App] Plan Expire',
                                       recipient=['ma7dev@gmail.com', 'chase@shopifiedapp.com'],
                                       data=data,
                                       nl2br=False)
