from shopified_core.commands import DropifiedBaseCommand
from django.utils import timezone
from django.core.cache import cache

import arrow
import requests
import time
from simplejson import JSONDecodeError

from ebay_core.models import EbayOrderTrack
from ebay_core import utils

from lib.exceptions import capture_exception, capture_message
from metrics.tasks import add_number_metric


class Command(DropifiedBaseCommand):
    help = 'Auto fulfill tracked orders with a tracking number and unfulfilled status'

    def add_arguments(self, parser):
        parser.add_argument(
            '--store', dest='store', action='store', type=int,
            help='Fulfill orders for the given store')

        parser.add_argument(
            '--max', dest='max', action='store', type=int, default=500,
            help='Fulfill orders count limit')

        parser.add_argument(
            '--uptime', dest='uptime', action='store', type=float, default=8,
            help='Maximum task uptime (minutes)')

    def start_command(self, *args, **options):
        fulfill_store = options.get('store')
        fulfill_max = options.get('max')
        uptime = options.get('uptime')

        orders = EbayOrderTrack.objects.exclude(ebay_status='fulfilled') \
                                       .exclude(source_tracking='') \
                                       .filter(hidden=False) \
                                       .filter(created_at__gte=arrow.now().replace(days=-30).datetime) \
                                       .filter(store__is_active=True) \
                                       .filter(store__auto_fulfill='enable') \
                                       .defer('data') \
                                       .order_by('-id')

        if len(orders) == 0:
            self.write("There aren't eBay orders for auto fulfill")
            add_number_metric.apply_async(args=['order.auto.fulfilled', 'ebay', 0], expires=500)
            return

        if fulfill_store is not None:
            orders = orders.filter(store=fulfill_store)

        fulfill_max = min(fulfill_max, len(orders)) if fulfill_max else len(orders)
        self.write(f'Auto Fulfill {fulfill_max}/{len(orders)} eBay Orders')

        utils.cache_fulfillment_data(orders, fulfill_max, output=self)
        self.write('eBay Cache data loaded')

        self.store_countdown = {}
        self.start_at = timezone.now()

        counter = {'fulfilled': 0, 'need_fulfill': 0}

        for order in orders[:fulfill_max]:
            try:
                counter['need_fulfill'] += 1

                if utils.cached_order_line_fulfillment_status(order):
                    self.write(f'Already fulfilled #{order.order_id} in [{order.store.title}]')
                    order.ebay_status = 'fulfilled'
                    order.save()
                    continue

                if self.fulfill_order(order):
                    order.ebay_status = 'fulfilled'
                    order.auto_fulfilled = True
                    order.save()

                    counter['fulfilled'] += 1
                    if counter['fulfilled'] % 50 == 0 or counter['fulfilled'] == 1:
                        self.write(f"Fulfill Progress: {counter['fulfilled']}")
                else:
                    cache_key = f'ebay_track_error_{order.id}'
                    error_count = cache.get(cache_key, 0)

                    if error_count > 10:
                        order.hidden = True
                        order.save()

                        capture_message('Ignore Order Track', level='warning', extra={
                            'type': 'eBay',
                            'id': order.id,
                            'errors': 'eBay'
                        }, tags={
                            'type': 'ebay'
                        })
                    else:
                        cache.set(cache_key, error_count + 1, timeout=3600)

                if (timezone.now() - self.start_at) > timezone.timedelta(seconds=uptime * 60):
                    extra = {'delta': (timezone.now() - self.start_at).total_seconds()}
                    capture_message('Auto fulfill taking too long', level="warning", extra=extra)
                    break

            except:
                capture_exception()

        self.write(f"Fulfilled eBay Orders: {counter['fulfilled']} / {counter['need_fulfill']}")

        add_number_metric.apply_async(args=['order.auto.fulfilled', 'ebay', counter['fulfilled']], expires=500)

    def fulfill_order(self, order_track):
        store = order_track.store
        user = store.user
        api_data = utils.order_track_fulfillment(order_track=order_track, user_config=user.get_config())

        fulfilled = False
        tries = 3
        ebay_utils = utils.EbayUtils(user)

        while tries > 0:
            r = None
            try:
                r = ebay_utils.api.update_order_details(order_track.order_id, api_data)
                r.raise_for_status()
                fulfilled = r.json().get('ok')

            except (JSONDecodeError, requests.exceptions.ConnectionError):
                self.write('Sleep for 2 sec')
                time.sleep(2)
                continue

            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 500:
                    # Wait and retry
                    self.write('Sleep for 5 sec')
                    time.sleep(5)
                    continue

                elif e.response.status_code == 404:
                    self.write(f'Not found #{order_track.order_id} in [{store.title}]')
                    order_track.delete()

                    return False

                else:
                    extra = {'order_track': order_track.id, 'response': r.text if r else ''}
                    capture_exception(extra=extra)

            except:
                capture_exception()

            finally:
                tries -= 1

        if fulfilled:
            countdown = self.store_countdown.get(store.id, 30)
            self.store_countdown[store.id] = countdown + 5

        return fulfilled
