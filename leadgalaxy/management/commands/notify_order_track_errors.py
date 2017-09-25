from django.core.management.base import BaseCommand
from raven.contrib.django.raven_compat.models import client as raven_client

from leadgalaxy.models import *
from shopified_core.utils import send_email_from_template


class Command(BaseCommand):
    def add_arguments(self, parser):
        pass

    def handle(self, *args, **options):
        try:
            self.start_command(*args, **options)
        except:
            raven_client.captureException()

    def start_command(self, *args, **options):
        for profile in UserProfile.objects.filter(subuser_parent__isnull=True):
            user = profile.user
            tracks = ShopifyOrderTrack.objects.filter(user=user, errors__gte=4)
            orders_track_visited_at = profile.get_config_value('orders_track_visited_at', None)
            if orders_track_visited_at:
                visited_time = arrow.get(orders_track_visited_at).datetime
                tracks = tracks.filter(updated_at__gte=visited_time)
            errors = tracks.count()
            if errors:
                data = {
                    'username': user.username,
                    'errors': errors,
                }
                send_email_from_template(
                    tpl='order_track_errors_notification.html',
                    subject='[Dropified] Order Track Errors Notification',
                    recipient=[user.email],
                    data=data,
                    nl2br=False,
                    from_email='"Dropified" <no-reply@dropified.com>')
