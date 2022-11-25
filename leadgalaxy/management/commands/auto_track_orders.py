from django.utils import timezone

import arrow
import json
import time

from aliexpress_core.models import AliexpressAccount
from shopified_core.commands import DropifiedBaseCommand
from leadgalaxy.models import ShopifyOrderTrack
from shopify_orders.models import ShopifyOrderLog

from shopify_orders import tasks as shopify_orders_tasks
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
        # track_max = options.get('max')
        # uptime = options.get('uptime')
        days = options.get('days')

        user_ids = AliexpressAccount.objects.all().values_list('user', flat=True).distinct()

        orders = ShopifyOrderTrack.objects.filter(user__in=user_ids) \
            .filter(shopify_status='') \
            .filter(source_tracking='') \
            .filter(hidden=False) \
            .filter(created_at__gte=arrow.now().replace(days=-days).datetime) \
            .filter(store__is_active=True) \
            .filter(store__auto_fulfill='enable') \
            .order_by('-created_at')

        if order_store is not None:
            orders = orders.filter(store=order_store)

        if options['count_only']:
            self.write(f'Orders to auto track {orders.count()}')
            return

        self.write(f'Started Auto tracking Shopify orders with count {orders.count()} on {arrow.now().datetime}')

        if options['progress']:
            self.progress_total(orders.count())

        if options['progress']:
            self.progress_total(orders.count())

        counter = {
            'tracked': 0,
            'need_tracking': 0,
            'skipped': 0,
            'status_update': 0
        }

        self.store_countdown = {}
        self.start_at = timezone.now()

        for order in orders:
            try:
                counter['need_tracking'] += 1
                user = order.store.user
                data = shopify_orders_tasks.get_order_info_via_api(order, order.source_id, order.store.id, 'shopify', user)
                time.sleep(.1)
                if isinstance(data, str):
                    self.write(f"Skipping tracking orders for user {user}: {data}")
                    continue
                if data and not data.get('error_msg'):
                    new_tracking_number = (data.get('tracking_number') and data.get('tracking_number') not in order.source_tracking)
                    if new_tracking_number:
                        self.write(f"Adding tracking number to {order.store} with order id {order.order_id}")
                        self.add_tracking_number_to_order(order, user, data)
                        counter['tracked'] += 1
                    else:
                        self.write(f"No new tracking number found for {order.order_id} for store {order.store}")
                        if data.get('status') != order.source_status:  # Save the new Aliexpress Order status
                            order.source_status = data.get('status')
                            order.save()
                            self.write(f"Changed Status to {data.get('status')} for {order.store} with order id {order.order_id}-{order.line_id}")
                            counter['status_update'] += 1
                            self.addShopifyOrderLogs(order, user, ' New Order Status saved via Quick Tracking')
                        else:
                            counter['skipped'] += 1
                else:  # No data would mean error querying Aliexpress API
                    self.write(f"Skipping tracking order with Id {order.order_id} for store {order.store} due to an error - {data.get('error_msg')}")
                    counter['skipped'] += 1
                    continue
                if not options['progress'] and counter['tracked'] % 50 == 0:
                    self.write('Tracking Progress: %d' % counter['tracked'])
            except Exception as e:
                capture_exception(e)

        self.write(f"Tracked Orders API:{counter['tracked']}/{counter['need_tracking']}"
                   f"- Skipped: {counter['skipped']} - Status Change: {counter['status_update']}")

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

        # order_data['aliexpress']['end_reason'] = data.get('end_reason')
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
            capture_exception(e)

        self.addShopifyOrderLogs(order, user, 'Tracking Number Added via API')

        if order.data and order.errors != -1:
            shopify_orders_tasks.check_track_errors.delay(order.id)

    def addShopifyOrderLogs(self, order, user, log_message):
        ShopifyOrderLog.objects.update_order_log(
            store=order.store,
            user=user,
            log=log_message,
            level='info',
            icon='truck',
            order_id=order.order_id,
            line_id=order.line_id
        )
