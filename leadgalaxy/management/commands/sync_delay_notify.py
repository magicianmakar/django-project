import requests
import json

from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from lib.exceptions import capture_exception

from leadgalaxy.models import UserProfile, ShopifyOrderTrack
from shopified_core.commands import DropifiedBaseCommand
from shopified_core.utils import (
    safe_int,
    app_link,
    send_email_from_template,
    using_replica,
)


class Command(DropifiedBaseCommand):

    def add_arguments(self, parser):
        parser.add_argument('--replica', dest='replica', action='store_true', help='Use Replica database if available')

    def start_command(self, *args, **options):
        profiles = UserProfile.objects.select_related('user') \
            .filter(subuser_parent=None) \
            .exclude(Q(sync_delay_notify=0) | Q(sync_delay_notify=None))

        emails = []
        tracking_page_url = app_link('orders/track', tracking=0, days_passed='expired')

        for profile in profiles:
            user = profile.user
            notify_days = safe_int(user.get_config('sync_delay_notify_days'), 0)
            if not notify_days or not (user.get_config('sync_delay_notify_email') or user.get_config('sync_delay_notify_push')):
                continue

            time_threshold = timezone.now() - timezone.timedelta(days=notify_days)
            time_threshold_prior = timezone.now() - timezone.timedelta(days=30)
            delayed_orders_count = using_replica(ShopifyOrderTrack, options['replica']) \
                .filter(user=user) \
                .filter(source_tracking='') \
                .filter(created_at__lt=time_threshold) \
                .filter(created_at__gt=time_threshold_prior) \
                .exclude(shopify_status='fulfilled') \
                .exclude(hidden=True) \
                .filter(store__is_active=True) \
                .filter(store__auto_fulfill='enable') \
                .count()

            if not delayed_orders_count:
                continue

            if user.get_config('sync_delay_notify_email'):
                try:
                    send_email_from_template(
                        tpl='order_sync_delay_notification.html',
                        subject="[Dropified] Orders Syncing Delay",
                        recipient=user.email,
                        data={
                            'url': tracking_page_url,
                            'count': delayed_orders_count,
                        }
                    )

                    self.write_success('Notified {} orders to {}'.format(delayed_orders_count, user.email))

                except:
                    capture_exception()

            if user.get_config('sync_delay_notify_push'):
                emails.append(user.email)

        if len(emails) and settings.ONESIGNAL_API_KEY and settings.ONESIGNAL_APP_ID:
            header = {
                "Content-Type": "application/json; charset=utf-8",
                "Authorization": "Basic " + settings.ONESIGNAL_API_KEY
            }

            emails_filters = []
            for email in emails:
                if len(emails_filters) > 0:
                    emails_filters.append({"operator": "OR"})
                emails_filters.append({"field": "email", "value": email})

            payload = {
                "app_id": settings.ONESIGNAL_APP_ID,
                "filters": emails_filters,
                "contents": {"en": "[Dropified] Orders Syncing Delay"},
                "url": tracking_page_url
            }

            req = requests.post("https://onesignal.com/api/v1/notifications", headers=header, data=json.dumps(payload))
            if req.status_code == 200:
                self.write_success('Notified to {} users'.format(len(emails)))
