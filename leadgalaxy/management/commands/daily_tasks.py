from django.utils import timezone

import arrow

from leadgalaxy.models import UserProfile, AppPermission
from leadgalaxy.utils import get_plan
from product_alerts.models import ProductChange
from shopified_core.commands import DropifiedBaseCommand
from shopified_core.utils import send_email_from_template
from stripe_subscription.utils import invoice_extra_stores, invoice_extra_subusers
from shopify_subscription.models import ShopifySubscription


class Command(DropifiedBaseCommand):
    def start_command(self, *args, **options):
        self.remove_blacklisted_permissions()

        # Disable affiliates
        for u in UserProfile.objects.filter(config__contains="_disable_affiliate"):
            u.del_config_values('_disable_affiliate')

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

        # Invoice Extra Subusers
        self.stdout.write('Invoice Extra Sub Users', self.style.HTTP_INFO)
        invoice_extra_subusers()

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
                plan_slug='free-shopify-2022'))

            i.charge_type = 'xexpired'
            i.save()

    def remove_blacklisted_permissions(self):
        perms_blacklist = [
            'admitad_affiliate.use',
            'aliexpress_affiliate.use',
            'aliexpress_mobile_order.use',
            'ebay_manual_affiliate_link.use'
        ]

        for name in perms_blacklist:
            permission = AppPermission.objects.get(name=name)
            for plan in permission.groupplan_set.all():
                plan.permissions.remove(permission)
