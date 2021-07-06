from django.utils import timezone

import time

import arrow
import requests

from simplejson import JSONDecodeError

from metrics.tasks import add_number_metric
from shopified_core.utils import http_exception_response, using_replica, last_executed
from shopified_core.commands import DropifiedBaseCommand
from leadgalaxy.models import ShopifyOrderTrack
from shopify_orders.models import ShopifyOrderLog
from leadgalaxy import utils
from leadgalaxy import tasks

from lib.exceptions import capture_exception, capture_message


class Command(DropifiedBaseCommand):
    help = 'Auto fulfill tracked orders with a tracking number and unfulfilled status'

    def add_arguments(self, parser):
        parser.add_argument('--store', action='store', type=int, help='Fulfill orders for the given store')
        parser.add_argument('--days', action='store', type=int, default=30, help='Fulfill orders created this number of days ago.')
        parser.add_argument('--max', action='store', type=int, default=500, help='Fulfill orders count limit')
        parser.add_argument('--uptime', action='store', type=float, default=8, help='Maximuim task uptime (minutes)')

        parser.add_argument('--new', action='store_true', help='Fulfill newest orders first')
        parser.add_argument('--progress', action='store_true', help='Show Reset Progress')
        parser.add_argument('--replica', dest='replica', action='store_true', help='Use Replica database if available')
        parser.add_argument('--count-only', dest='count_only', action='store_true', help='Use Replica database if available')

    def start_command(self, *args, **options):
        fulfill_store = options.get('store')
        fulfill_max = options.get('max')
        uptime = options.get('uptime')
        days = options.get('days')

        orders = using_replica(ShopifyOrderTrack, options['replica']) \
            .filter(shopify_status='') \
            .exclude(source_tracking='') \
            .filter(hidden=False) \
            .filter(created_at__gte=arrow.now().replace(days=-days).datetime) \
            .filter(store__is_active=True) \
            .filter(store__auto_fulfill='enable') \
            .defer('data') \
            .order_by('-created_at' if options['new'] else 'created_at')

        if fulfill_store is not None:
            orders = orders.filter(store=fulfill_store)

        if options['count_only']:
            self.write(f'Orders to auto fulfill {orders.count()}')
            return

        self.write('Start Auto Fulfill')

        if options['progress']:
            self.progress_total(orders.count())

        counter = {
            'fulfilled': 0,
            'need_fulfill': 0,
            'skipped': 0,
        }

        self.store_countdown = {}
        self.store_locations = {}
        self.start_at = timezone.now()

        if fulfill_max:
            orders = orders[:fulfill_max]

        for order in orders:
            if options['progress']:
                self.progress_update(desc=order.store.shop)

            try:
                counter['need_fulfill'] += 1

                if last_executed(f'order-auto-fulfill2-{order.id}', 21600):
                    if not last_executed(f'order-auto-fulfill-sync-{order.id}', 21600):
                        utils.get_tracking_orders(order.store, [order])

                    self.progress_write(f'Skipping Order #{order.id} for {order.store.shop}')
                    counter['skipped'] += 1
                    continue

                if self.fulfill_order(order):
                    order.shopify_status = 'fulfilled'
                    order.auto_fulfilled = True
                    order.save()

                    counter['fulfilled'] += 1
                    if not options['progress'] and counter['fulfilled'] % 50 == 0:
                        self.write('Fulfill Progress: %d' % counter['fulfilled'])

                if (timezone.now() - self.start_at) > timezone.timedelta(seconds=uptime * 60):
                    capture_message(
                        'Auto fulfill taking too long',
                        level="warning",
                        extra={'delta': (timezone.now() - self.start_at).total_seconds()})

                    break
            except:
                capture_exception()

        self.write(f"Fulfilled Orders: {counter['fulfilled']} / {counter['need_fulfill']} - Skipped: {counter['skipped']}")

        add_number_metric.apply_async(args=['order.auto.fulfilled', 'shopify', counter['fulfilled']], expires=500)
        add_number_metric.apply_async(args=['order.auto.skipped', 'shopify', counter['skipped']], expires=500)

    def fulfill_order(self, order):
        store = order.store
        user = store.user

        # self.raven_context_from_store(raven_client, store, tags={'order': order.order_id, 'track': order.id})

        api_data, line = utils.order_track_fulfillment(
            order_track=order,
            user_config=user.get_config(),
            return_line=True,
            location_id=self.store_locations.get(order.store.id))

        locations = []
        trying_locations = False
        fulfilled = False
        check_order_exist = True
        tries = 3

        while tries > 0 or locations:
            if tries < -3:
                capture_message('Fulfillment Loop Detected')
                break

            try:
                rep = requests.post(
                    url=store.api('orders', order.order_id, 'fulfillments'),
                    json=api_data
                )

                rep.raise_for_status()

                fulfilled = 'fulfillment' in rep.json()
                if fulfilled:
                    fulfillment = rep.json()['fulfillment']
                    if fulfillment['status'] == 'pending':
                        r = requests.post(
                            url=store.api('orders', order.order_id, 'fulfillments', fulfillment['id'], 'complete'),
                            json=api_data
                        )

                break

            except (JSONDecodeError, requests.exceptions.ConnectTimeout):
                self.write('Sleep for 2 sec')
                time.sleep(2)
                continue
            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 429:
                    # Wait and retry
                    self.write('Sleep for 5 sec')
                    time.sleep(5)
                    continue

                elif e.response.status_code in [422, 404]:
                    if e.response.status_code == 404:
                        if check_order_exist:
                            r = requests.get(store.api(f'orders/{order.order_id}'))
                            if r.status_code == 404:
                                self.log_fulfill_error(order, 'Order Not Found')

                                self.write('Not found #{} in [{}]'.format(order.order_id, order.store.title))
                                order.hidden = True
                                order.save()

                                return False

                            elif r.ok and order.line_id not in [i['id'] for i in r.json()['order']['line_items']]:
                                self.log_fulfill_error(order, 'Order Line Not Found')
                                self.write('Line Not found #{} in [{}]'.format(order.order_id, order.store.title))
                                order.hidden = True
                                order.save()

                                return False

                            else:
                                check_order_exist = False

                    if 'already fulfilled' in rep.text:
                        # Mark as fulfilled but not auto-fulfilled
                        self.write('Already fulfilled #{} in [{}]'.format(order.order_id, order.store.title))
                        order.shopify_status = 'fulfilled'
                        order.save()

                        self.log_fulfill_error(order, 'Order is already fulfilled')

                        return False

                    elif 'Invalid fulfillment order line item quantity requested' in rep.text:
                        # This could mean it was fulfilled
                        r = requests.get(url=store.api(f'orders/{order.order_id}/fulfillments'))
                        if r.ok:

                            for fulfillment in r.json()['fulfillments']:
                                for line in fulfillment['line_items']:
                                    if line['id'] == order.line_id:
                                        if line['fulfillment_status'] == 'fulfilled':
                                            # Mark as fulfilled but not auto-fulfilled
                                            self.write(f'Already have fulfillment #{order.order_id} in {order.store.shop}')
                                            order.shopify_status = 'fulfilled'
                                            order.save()

                                            self.log_fulfill_error(order, 'Order is already fulfilled')

                                            return False

                        capture_message('Invalid fulfillment order line', extra={
                            'shop': order.store.shop,
                            'order_track': order.id,
                            'r': r.text,
                            'rep': rep.text
                        })

                    elif 'This order has been canceled' in rep.text:
                        self.write('Order has been canceled #{} in [{}]'.format(order.order_id, order.store.title))
                        order.hidden = True
                        order.save()

                        self.log_fulfill_error(order, 'This order has been canceled')

                        return False

                    elif 'invalid for this fulfillment service' in rep.text:
                        # Using a different fulfillment_service (i.e: amazon_marketplace_web)
                        self.write('Invalid for this fulfillment service #{} in [{}]'.format(order.order_id, order.store.title))
                        order.shopify_status = 'fulfilled'
                        order.save()

                        self.log_fulfill_error(order, 'Invalid for this fulfillment service')

                        return False

                    elif 'your shop does not have the \'oberlo\' fulfillment service enabled' in rep.text.lower():
                        r = requests.post(
                            url=store.api('fulfillment_services'),
                            json={
                                "fulfillment_service": {
                                    "name": "Oberlo",
                                    "inventory_management": False,
                                    "tracking_support": False,
                                    "requires_shipping_method": False,
                                    "format": "json"
                                }
                            }
                        )

                        if r.ok:
                            continue
                        else:

                            capture_message('Add Fulfillment Error', extra={
                                'order_track': order.id,
                                'response': r.text
                            }, level='warning')

                            r = requests.post(
                                url=store.api('fulfillment_services'),
                                json={
                                    "fulfillment_service": {
                                        "name": "oberlo",
                                        "inventory_management": False,
                                        "tracking_support": False,
                                        "requires_shipping_method": False,
                                        "format": "json"
                                    }
                                }
                            )

                            if r.ok:
                                continue
                            else:
                                capture_message('Add Fulfillment Workarround Error', extra={
                                    'order_track': order.id,
                                    'response': r.text
                                })

                                return False

                    elif "Your shop does not have the 'Manual' fulfillment service enabled" in rep.text:
                        order.hidden = True
                        order.save()

                        self.log_fulfill_error(order, 'Shopify Manual Fulfillement bug')

                        capture_exception(extra={
                            'order_track': order.id,
                            'response': rep.text
                        })

                        return False

                    elif "fulfilled quantity must be greater than zero" in rep.text.lower():
                        order.hidden = True
                        order.save()

                        self.log_fulfill_error(order, 'Cancelled Order item')

                        return False

                    elif 'must be stocked at the same location' in rep.text.lower() \
                            or 'none of the items are stocked at the new location' in rep.text.lower() \
                            or 'could not reassign inventory' in rep.text.lower() \
                            or e.response.status_code == 404:

                        location = None

                        if locations:
                            # We are trying locations one by one
                            location = locations.pop()
                            self.write(f"Re-trying location {location['name']} ({location['id']}) for order #{order.order_id} in {order.store.shop}")

                            if not locations:
                                # Make sure we don't escape the last location is len(locations) > 3
                                tries += 1

                        elif not trying_locations:
                            # Try locations one by one
                            locations = store.get_locations()
                            location = locations.pop()

                            trying_locations = True

                            self.write(f"Trying location {location['name']} ({location['id']}) for order #{order.order_id} in {order.store.shop}")

                        if location:
                            api_data["fulfillment"]["location_id"] = location['id']

                            self.store_locations[order.store.id] = location['id']
                        else:
                            capture_message('No location found', extra={'track': order.id, 'store': order.store.shop})

                            self.log_fulfill_error(order, 'No location found', shopify_api=False)

                            order.hidden = True
                            order.save()

                        continue

                elif locations:
                    # we are trying locations but we don't hand this excption
                    capture_message('Unhandled Shopify status Loop Detected', extra=http_exception_response(e))
                    locations = []

                elif e.response.status_code in [401, 402, 403]:
                    self.log_fulfill_error(order, 'API Authorization ({})'.format(e.response.status_code))

                    order.hidden = True
                    order.save()

                    return False

                if "An error occurred, please try again" not in rep.text:
                    capture_exception(extra={
                        'order_track': order.id,
                        'response': rep.text
                    })

            except Exception as e:
                capture_exception(extra=http_exception_response(e))
            finally:
                tries -= 1

        if fulfilled:
            if user.get_config('aliexpress_as_notes', True):
                note = "Auto Fulfilled by Dropified (Item #{} - Confirmation Email: {})".format(
                    order.line_id, 'Yes' if api_data['fulfillment'].get('notify_customer') else 'No')

                countdown = self.store_countdown.get(store.id, 30)
                tasks.add_ordered_note.apply_async(args=[store.id, order.order_id, note], countdown=countdown)

                self.store_countdown[store.id] = countdown + 5

            if line:
                line.fulfillment_status = 'fulfilled'
                line.save()

            ShopifyOrderLog.objects.update_order_log(
                store=store,
                user=None,
                log='Marked as fulfilled By Dropified',
                level='success',
                icon='check',
                order_id=order.order_id,
                line_id=order.line_id
            )

        return fulfilled

    def log_fulfill_error(self, order, msg, shopify_api=True):
        if shopify_api:
            msg = 'Shopify API Error: {}'.format(msg)

        ShopifyOrderLog.objects.update_order_log(
            store=order.store,
            user=None,
            log=msg,
            level='error',
            icon='times',
            order_id=order.order_id,
            line_id=order.line_id
        )
