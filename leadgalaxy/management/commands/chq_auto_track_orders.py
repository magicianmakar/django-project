from django.utils import timezone

import json
import arrow

from shopified_core.commands import DropifiedBaseCommand
from commercehq_core.models import CommerceHQOrderTrack

from shopify_orders import tasks as orders_tasks
from lib.exceptions import capture_exception


class Command(DropifiedBaseCommand):
    help = 'Automatically add tracking numbers to orders'

    def add_arguments(self, parser):
        parser.add_argument('--store', action='store', type=int, help='Fulfill orders for the given store')
        parser.add_argument('--days', action='store', type=int, default=30, help='Auto Track orders created this number of days ago.')
        parser.add_argument('--max', action='store', type=int, default=500, help='Orders track count limit')
        parser.add_argument('--uptime', action='store', type=float, default=8, help='Maximuim task uptime (minutes)')

        parser.add_argument('--new', action='store_true', help='Auro track newest orders first')
        parser.add_argument('--progress', action='store_true', help='Show Reset Progress')
        parser.add_argument('--count-only', dest='count_only', action='store_true', help='Show total order count to be tracked')

    def start_command(self, *args, **options):
        order_store = options.get('store')
        track_max = options.get('max')
        # uptime = options.get('uptime')
        days = options.get('days')

        orders = CommerceHQOrderTrack.objects.filter(commercehq_status='') \
            .filter(source_tracking='') \
            .filter(hidden=False) \
            .filter(created_at__gte=arrow.now().replace(days=-days).datetime) \
            .filter(store__is_active=True) \
            .filter(store__auto_fulfill='enable') \
            .defer('data') \
            .order_by('-created_at' if options['new'] else 'created_at')

        if order_store is not None:
            orders = orders.filter(store=order_store)

        if options['count_only']:
            self.write(f'Orders to auto track {orders.count()}')
            return

        self.write('Started Auto tracking orders')

        if options['progress']:
            self.progress_total(orders.count())

        if options['progress']:
            self.progress_total(orders.count())

        counter = {
            'tracked': 0,
            'need_tracking': 0,
            'skipped': 0,
        }

        self.store_countdown = {}
        self.start_at = timezone.now()

        if track_max:
            orders = orders[:track_max]

        for order in orders:
            try:
                counter['need_tracking'] += 1
                user = order.store.user
                data = orders_tasks.get_order_info_via_api(order, order.source_id, order.store.id, 'chq', user)
                if data and not data.get('error_msg'):
                    new_tracking_number = (data.get('tracking_number') and data.get('tracking_number') not in order.source_tracking)
                    if data.get('tracking_number') != '' and new_tracking_number:
                        self.add_tracking_number_to_order(order, user, data)
                        counter['tracked'] += 1
                    else:
                        counter['skipped'] += 1
                        self.write(f"Skipping tracking order with Id {order.order_id} for store {order.store} because there is no new data")
                        if data.get('status') != order.source_status:  # Save the new Aliexpress Order status
                            order.source_status = data.get('status')
                            order.save()
                else:  # No data would mean error querying Aliexpress API
                    self.write(f"Skipping tracking order with Id {order.order_id} for store {order.store} due to an error")
                    counter['skipped'] += 1
                    continue
                if not options['progress'] and counter['tracked'] % 50 == 0:
                    self.write('Tracking Progress: %d' % counter['tracked'])
            except Exception as e:
                capture_exception(e)

        self.write(f"Tracked Orders: {counter['tracked']} / {counter['need_tracking']} - Skipped: {counter['skipped']}")

    def add_tracking_number_to_order(self, order, user, data):
        # models_user = user.models_user
        order.source_status = data.get('status')
        order.source_status_details = data.get('orderStatus')
        order.source_tracking = data.get('tracking_number')
        order.status_updated_at = timezone.now()
        try:
            order_data = json.loads(order.data)
            if 'aliexpress' not in order_data:
                order_data['aliexpress'] = {}
        except:
            order_data = {'aliexpress': {}}

        order_data['aliexpress']['end_reason'] = data.get('end_reason')
        order_details = {}
        try:
            if data.get('order_details'):
                order_details = data.get('order_details')
                order_data['aliexpress']['order_details'] = order_details
        except:
            capture_exception(level='warning')

        order.data = json.dumps(order_data)
        try:
            order.save()
        except Exception as e:
            print(e)
