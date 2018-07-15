from django.utils import timezone

import arrow

from leadgalaxy.models import *
from product_alerts.models import ProductChange
from shopified_core.management import DropifiedBaseCommand
from stripe_subscription.utils import invoice_extra_stores


class Command(DropifiedBaseCommand):
    def start_command(self, *args, **options):
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
        self.stdout.write('Inoice Extra Stores', self.style.HTTP_INFO)
        invoice_extra_stores()

        self.stdout.write('Delete Old Alerts', self.style.HTTP_INFO)
        self.delete_alerts()

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
            data=data)

    def delete_alerts(self):
        # Remove alerts after 30 days
        delete_date = arrow.utcnow().replace(days=-30).datetime
        alert_ids = list(ProductChange.objects.filter(created_at__lt=delete_date).values_list('id', flat=True))
        alerts_count = len(alert_ids)

        self.stdout.write('Delete {} Alerts'.format(alerts_count))

        steps = 10000
        start = 0
        while start < alerts_count:
            order_ids = alert_ids[start:start + steps]
            ProductChange.objects.filter(id__in=order_ids).delete()

            start += steps
