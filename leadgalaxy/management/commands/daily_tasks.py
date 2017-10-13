from django.utils import timezone

import arrow

from leadgalaxy.models import *
from shopified_core.management import DropifiedBaseCommand


class Command(DropifiedBaseCommand):
    def start_command(self, *args, **options):
        # Archive alerts after 7 days
        archive_date = arrow.utcnow().replace(days=-7).datetime
        AliexpressProductChange.objects.filter(hidden=False, created_at__lt=archive_date).update(hidden=True)

        # Remove alerts after 30 days
        delete_date = arrow.utcnow().replace(days=-30).datetime
        AliexpressProductChange.objects.filter(created_at__lt=delete_date).delete()

        # Expired plans
        self.stdout.write('Change plan of expired profiles', self.style.HTTP_INFO)
        for profile in UserProfile.objects.filter(plan_expire_at__lte=timezone.now()):
            if profile.plan_after_expire:
                self.stdout.write(u'Changing: {}'.format(profile.user.username))
                self.profile_changed(profile, profile.plan, profile.plan_after_expire)

                profile.plan = profile.plan_after_expire
                profile.plan_after_expire = None
                profile.plan_expire_at = None
                profile.save()

        # Invoice Extra Stores
        from stripe_subscription.utils import invoice_extra_stores
        invoice_extra_stores()

    def profile_changed(self, profile, expired_plan, new_plan):
        data = {
            'profile': profile,
            'expired_plan': expired_plan,
            'new_plan': new_plan
        }

        from shopified_core.utils import send_email_from_template

        send_email_from_template(
            tpl='expire_plan_change.html',
            subject='[Dropified] Plan Expire',
            recipient=['ma7dev@gmail.com', 'chase@dropified.com'],
            data=data,
            nl2br=False)
