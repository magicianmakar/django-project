from django.utils import timezone
from django.core.cache import cache

import arrow
import requests
import time
from simplejson import JSONDecodeError

from shopified_core.commands import DropifiedBaseCommand
from bigcommerce_core.models import BigCommerceOrderTrack
from bigcommerce_core import utils
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

        orders = BigCommerceOrderTrack.objects.exclude(bigcommerce_status='fulfilled') \
                                      .exclude(source_tracking='') \
                                      .filter(hidden=False) \
                                      .filter(created_at__gte=arrow.now().replace(days=-30).datetime) \
                                      .filter(store__is_active=True) \
                                      .filter(store__auto_fulfill='enable') \
                                      .defer('data') \
                                      .order_by('-id')
        if fulfill_store is not None:
            orders = orders.filter(store=fulfill_store)

        fulfill_max = min(fulfill_max, len(orders)) if fulfill_max else len(orders)
        utils.cache_fulfillment_data(orders, fulfill_max)

        self.write('Auto Fulfill {}/{} BigCommerce Orders'.format(fulfill_max, len(orders)), self.style.HTTP_INFO)
        self.store_countdown = {}
        self.start_at = timezone.now()

        counter = {'fulfilled': 0, 'need_fulfill': 0}

        for order in orders[:fulfill_max]:
            try:
                counter['need_fulfill'] += 1

                if self.fulfill_order(order):
                    order.bigcommerce_status = 'fulfilled'
                    order.auto_fulfilled = True
                    order.save()

                    counter['fulfilled'] += 1
                    if counter['fulfilled'] % 50 == 0:
                        self.write('Fulfill Progress: %d' % counter['fulfilled'])
                else:
                    cache_key = 'bigcommerce_track_error_{}'.format(order.id)
                    error_count = cache.get(cache_key, 0)

                    if error_count > 10:
                        order.hidden = True
                        order.save()

                        capture_message('Ignore Order Track', level='warning', extra={
                            'type': 'bigcommerce',
                            'id': order.id,
                            'errors': 'bigcommerce'
                        }, tags={
                            'type': 'bigcommerce'
                        })
                    else:
                        cache.set(cache_key, error_count + 1, timeout=3600)

                if (timezone.now() - self.start_at) > timezone.timedelta(seconds=uptime * 60):
                    extra = {'delta': (timezone.now() - self.start_at).total_seconds()}
                    capture_message('Auto fulfill taking too long', level="warning", extra=extra)
                    break

            except:
                capture_exception()

        self.write('Fulfilled BigCommerce Orders: {fulfilled} / {need_fulfill}'.format(**counter))

        add_number_metric.apply_async(args=['order.auto.fulfilled', 'bigcommerce', counter['fulfilled']], expires=500)

    def fulfill_order(self, order_track):
        store = order_track.store
        user = store.user
        url = store.get_api_url('v2/orders', order_track.order_id, 'shipments')
        api_data = None

        fulfilled = False
        tries = 3

        while tries > 0:
            try:
                if not api_data:
                    api_data = utils.order_track_fulfillment(order_track=order_track, user_config=user.get_config())

                rep = store.request.post(url=url, json=api_data)
                rep.raise_for_status()
                fulfilled = 'id' in rep.json()
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

                elif e.response.status_code == 422:
                    if 'shipped count of a product exceeds quantity' in e.response.text.lower():
                        self.write('Already fulfilled #{} in [{}]'.format(order_track.order_id, store.title))
                        order_track.bigcommerce_status = 'fulfilled'
                        order_track.save()

                        return False

                    else:
                        capture_exception(
                            level='warning',
                            extra={'order_track': order_track.id, 'response': e.response.text}
                        )

                        return False

                elif e.response.status_code == 404:
                    self.write('Not found #{} in [{}]'.format(order_track.order_id, store.title))
                    order_track.delete()

                    return False

                elif e.response.status_code == 402:
                    order_track.hidden = True
                    order_track.save()

                    return False

                else:
                    extra = {'order_track': order_track.id, 'response': rep.text}
                    capture_exception(extra=extra)

            except:
                capture_exception()

            finally:
                tries -= 1

        if fulfilled:
            countdown = self.store_countdown.get(store.id, 30)
            self.store_countdown[store.id] = countdown + 5

        return fulfilled
