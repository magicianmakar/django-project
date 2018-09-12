from django.utils import timezone
from django.core.cache import caches

import arrow
import requests
import time
from simplejson import JSONDecodeError

from shopified_core.management import DropifiedBaseCommand
from commercehq_core.models import CommerceHQOrderTrack
from commercehq_core import utils

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

        orders = CommerceHQOrderTrack.objects.exclude(commercehq_status='fulfilled') \
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

        self.write('Auto Fulfill {}/{} CHQ Orders'.format(fulfill_max, len(orders)), self.style.HTTP_INFO)
        self.store_countdown = {}
        self.start_at = timezone.now()

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

        results = 'Fulfilled Orders: {fulfilled} / {need_fulfill}'.format(**counter)
        self.write(results)

    def fulfill_order(self, order_track):
        store = order_track.store
        user = store.user
        url = store.get_api_url('orders', order_track.order_id, 'shipments')
        api_data = None

        fulfilled = False
        tries = 3

        while tries > 0:
            try:
                if not api_data:
                    api_data = utils.order_track_fulfillment(order_track=order_track, user_config=user.get_config())

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
                    if 'shipped count of a product exceeds quantity' in e.response.text.lower():
                        self.write(u'Already fulfilled #{} in [{}]'.format(order_track.order_id, store.title))
                        order_track.commercehq_status = 'fulfilled'
                        order_track.save()

                        return False

                    elif 'fulfilment id is invalid' in e.response.text.lower():
                        caches['orders'].delete('chq_fulfilments_{}_{}_{}'.format(
                            store.id, order_track.order_id, api_data['data'][0]['items'][0]['id']))

                        api_data = None
                        continue

                    elif 'warehouse id' in e.response.text.lower() or 'Either fulfilment_id or array' in e.response.text:
                        order_track.hidden = True
                        order_track.save()

                        return False

                    else:
                        raven_client.captureException(
                            level='warning',
                            extra={'order_track': order_track.id, 'response': e.response.text}
                        )

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
