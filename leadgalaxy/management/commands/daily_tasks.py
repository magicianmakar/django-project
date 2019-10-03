from django.contrib.auth.models import User

from django.utils import timezone

import arrow

from leadgalaxy.models import UserProfile
from leadgalaxy.utils import get_plan
from product_alerts.models import ProductChange
from shopified_core.management import DropifiedBaseCommand
from shopified_core.utils import send_email_from_template
from stripe_subscription.utils import invoice_extra_stores
from shopify_subscription.models import ShopifySubscription


class Command(DropifiedBaseCommand):
    def start_command(self, *args, **options):
        # Disable affilaites
        for u in User.objects.filter(profile__config__contains="_disable_affiliate"):
            u.set_config('_disable_affiliate', False)

        # Expired plans
        self.stdout.write('Change plan of expired profiles', self.style.HTTP_INFO)
        for profile in UserProfile.objects.filter(plan_expire_at__lte=timezone.now()):
            if profile.plan_after_expire:
                self.stdout.write('Changing: {}'.format(profile.user.username))
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
        self.cancel_yearly()

    def profile_changed(self, profile, expired_plan, new_plan):
        send_email_from_template(
            tpl='expire_plan_change.html',
            subject='[Dropified] Plan Expire Notification',
            recipient=['support@dropified.com'],
            data={
                'profile': profile,
                'expired_plan': expired_plan,
                'new_plan': new_plan
            })

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

    def cancel_yearly(self):
        cancel_date = arrow.utcnow().replace(years=-1, days=-1).span('day')[1]
        users = ShopifySubscription.objects.filter(
            charge_type='single',
            plan__payment_gateway='shopify',
            plan__payment_interval='yearly',
            user__profile__plan__free_plan=False,
            status='active',
            created_at__lt=cancel_date.datetime)

        for i in users:
            self.stdout.write(f'Cancel yearly subscription for {i.user.email} from {i.created_at:%Y-%m-%d}')
            i.user.profile.change_plan(get_plan(
                payment_gateway='shopify',
                plan_slug='shopify-free-plan'))
