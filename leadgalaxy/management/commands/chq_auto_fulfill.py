from django.core.management.base import BaseCommand
from django.core.cache import cache
from django.utils import timezone

import requests
import time
from simplejson import JSONDecodeError

from commercehq_core.models import CommerceHQOrderTrack
from commercehq_core import utils

from raven.contrib.django.raven_compat.models import client as raven_client


class Command(BaseCommand):
    help = 'Auto fulfill tracked orders with a tracking number and unfulfilled status'

    def add_arguments(self, parser):
        parser.add_argument(
            '--threshold', dest='threshold', action='store', type=int, default=60,
            help='Fulfill orders updated before threshold (seconds)')

        parser.add_argument(
            '--store', dest='store', action='store', type=int,
            help='Fulfill orders for the given store')

        parser.add_argument(
            '--max', dest='max', action='store', type=int, default=500,
            help='Fulfill orders count limit')

        parser.add_argument(
            '--uptime', dest='uptime', action='store', type=float, default=8,
            help='Maximum task uptime (minutes)')

    def handle(self, *args, **options):
        try:
            self.start_command(*args, **options)
        except:
            raven_client.captureException()

    def write(self, msg, style_func=None, ending=None):
        self.stdout.write(msg, style_func, ending)

    def start_command(self, *args, **options):
        threshold = options.get('threshold')
        fulfill_store = options.get('store')
        fulfill_max = options.get('max')
        uptime = options.get('uptime')
        time_threshold = timezone.now() - timezone.timedelta(seconds=threshold)
        orders = CommerceHQOrderTrack.objects.exclude(commercehq_status='fulfilled') \
                                             .exclude(source_tracking='') \
                                             .exclude(hidden=True) \
                                             .filter(status_updated_at__lt=time_threshold) \
                                             .filter(store__is_active=True) \
                                             .defer('data') \
                                             .order_by('-id')
        if fulfill_store is not None:
            orders = orders.filter(store=fulfill_store)

        fulfill_max = min(fulfill_max, orders.count()) if fulfill_max else orders.count()
        cache_keys = utils.cache_fulfillment_data(orders, fulfill_max)

        self.write('Auto Fulfill {}/{} CHQ Orders'.format(fulfill_max, orders.count()), self.style.HTTP_INFO)
        self.store_countdown = {}
        self.start_at = timezone.now()
        self.fulfill_threshold = timezone.now() - timezone.timedelta(seconds=threshold * 60)

        counter = {'fulfilled': 0, 'need_fulfill': 0}

        for order in orders[:fulfill_max]:
            try:
                counter['need_fulfill'] += 1

                if self.fulfill_order(order):
                    order.commercehq_status = 'fulfilled'
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

        cache.delete_many(cache_keys)
        results = 'Fulfilled Orders: {fulfilled} / {need_fulfill}'.format(**counter)
        self.write(results)

    def fulfill_order(self, order_track):
        store = order_track.store
        user = store.user
        url = store.get_api_url('orders', order_track.order_id, 'shipments')
        api_data = utils.order_track_fulfillment(order_track=order_track, user_config=user.get_config())

        fulfilled = False
        tries = 3

        while tries > 0:
            try:
                rep = store.request.post(url=url, json=api_data)
                rep.raise_for_status()
                fulfilled = 'shipments' in rep.json()
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
                    message = e.response.json().get('message')
                    self.write(u'{} #{} in [{}]'.format(message, order_track.order_id, store.title))
                    order_track.commercehq_status = 'fulfilled'
                    order_track.save()

                    return False

                elif e.response.status_code == 404:
                    self.write(u'Not found #{} in [{}]'.format(order_track.order_id, store.title))
                    order_track.delete()

                    return False

                elif e.response.status_code == 402:
                    order_track.hidden = True
                    order_track.save()

                    return False

                else:
                    extra = {'order_track': order_track.id, 'response': rep.text}
                    raven_client.captureException(extra=extra)

            except:
                raven_client.captureException()

            finally:
                tries -= 1

        if fulfilled:
            countdown = self.store_countdown.get(store.id, 30)
            self.store_countdown[store.id] = countdown + 5

        return fulfilled
