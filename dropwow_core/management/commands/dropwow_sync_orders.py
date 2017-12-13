import arrow

from django.db.models import Q

from shopified_core.management import DropifiedBaseCommand
from leadgalaxy.models import ShopifyOrderTrack

from dropwow_core.models import DropwowOrderStatus
from dropwow_core.utils import get_dropwow_order


class Command(DropifiedBaseCommand):
    help = 'Fetch Order Statuses from Dropwow API and store them in the database'

    def start_command(self, *args, **options):
        tracks = ShopifyOrderTrack.objects.filter(source_type='dropwow') \
            .filter(created_at__gte=arrow.now().replace(days=-30).datetime) \
            .filter(Q(source_tracking='') | Q(source_tracking='0')) \
            .exclude(shopify_status='fulfilled') \
            .exclude(source_status__in=['D', 'I']) \
            .exclude(Q(source_id=None) | Q(source_id=''))

        self.write_success('Checking {} Tracks'.format(len(tracks)))

        for track in tracks:
            email = track.store.user.dropwow_account.email
            api_key = track.store.user.dropwow_account.api_key
            order_id = track.source_id
            try:
                res = get_dropwow_order(email, api_key, order_id)
                if str(res.get('order_id')) == order_id:
                    status = res.get('status', '')
                    tracking_number = res.get('tracking_number', '')
                    DropwowOrderStatus.objects.filter(order_id=order_id).update(
                        status=status,
                        tracking_number=tracking_number,
                        error_message='',
                    )

                    if track.source_status != status or track.source_tracking != tracking_number:
                        self.write_success('Dropwow Order Updated: {} - Status: {} -> {} - Tracking: {} -> {}'.format(
                            order_id, track.source_status, status, track.source_tracking, tracking_number))

                        track.source_status = status
                        track.source_tracking = tracking_number
                        track.save()

            except:
                DropwowOrderStatus.objects.filter(order_id=order_id).update(
                    error_message='Not Found',
                )

                self.stdout.write('Failed to fetch order status #{}'.format(order_id), self.style.WARNING)
