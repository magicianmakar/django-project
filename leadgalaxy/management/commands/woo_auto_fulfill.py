from shopified_core.management import DropifiedBaseCommand
from django.utils import timezone

import arrow
import requests
import time
from simplejson import JSONDecodeError

from woocommerce_core.models import WooOrderTrack
from woocommerce_core import utils

from raven.contrib.django.raven_compat.models import client as raven_client


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

        orders = WooOrderTrack.objects.exclude(woocommerce_status='fulfilled') \
                                      .exclude(source_tracking='') \
                                      .filter(hidden=False) \
                                      .filter(created_at__gte=arrow.now().replace(days=-30).datetime) \
                                      .filter(store__is_active=True) \
                                      .defer('data') \
                                      .order_by('-id')
        if fulfill_store is not None:
            orders = orders.filter(store=fulfill_store)

        fulfill_max = min(fulfill_max, len(orders)) if fulfill_max else len(orders)
        utils.cache_fulfillment_data(orders, fulfill_max)

        self.write('Auto Fulfill {}/{} WOO Orders'.format(fulfill_max, len(orders)), self.style.HTTP_INFO)
        self.store_countdown = {}
        self.start_at = timezone.now()

        counter = {'fulfilled': 0, 'need_fulfill': 0}

        for order in orders[:fulfill_max]:
            try:
                counter['need_fulfill'] += 1

                if utils.cached_order_line_fulfillment_status(order):
                    self.write(u'Already fulfilled #{} in [{}]'.format(order.order_id, order.store.title))
                    order.woocommerce_status = 'fulfilled'
                    order.save()
                    continue

                if self.fulfill_order(order):
                    order.woocommerce_status = 'fulfilled'
                    order.auto_fulfilled = True
                    order.save()

                    counter['fulfilled'] += 1
                    if counter['fulfilled'] % 50 == 0:
                        self.write('Fulfill Progress: %d' % counter['fulfilled'])

                if (timezone.now() - self.start_at) > timezone.timedelta(seconds=uptime * 60):
                    extra = {'delta': (timezone.now() - self.start_at).total_seconds()}
                    raven_client.captureMessage('Auto fulfill taking too long', level="warning", extra=extra)
                    break

            except:
                raven_client.captureException()

        results = 'Fulfilled Orders: {fulfilled} / {need_fulfill}'.format(**counter)
        self.write(results)

    def fulfill_order(self, order_track):
        store = order_track.store
        user = store.user
        api_data = utils.order_track_fulfillment(order_track=order_track, user_config=user.get_config())

        fulfilled = False
        tries = 3

        while tries > 0:
            try:
                r = store.wcapi.put('orders/{}'.format(order_track.order_id), api_data)
                r.raise_for_status()
                fulfilled = 'id' in r.json()
                if fulfilled and len(utils.get_unfulfilled_items(r.json())) == 0:
                    utils.update_order_status(store, order_track.order_id, 'completed')
                break

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
                    self.write(u'Not found #{} in [{}]'.format(order_track.order_id, store.title))
                    order_track.delete()

                    return False

                else:
                    extra = {'order_track': order_track.id, 'response': r.text}
                    raven_client.captureException(extra=extra)

            except:
                raven_client.captureException()

            finally:
                tries -= 1

        if fulfilled:
            countdown = self.store_countdown.get(store.id, 30)
            self.store_countdown[store.id] = countdown + 5

        return fulfilled
