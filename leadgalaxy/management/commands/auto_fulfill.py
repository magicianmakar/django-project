from django.utils import timezone

import requests
import time
from simplejson import JSONDecodeError

from shopified_core.management import DropifiedBaseCommand
from leadgalaxy.models import *
from leadgalaxy import utils
from leadgalaxy import tasks

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
            help='Maximuim task uptime (minutes)')

    def start_command(self, *args, **options):
        fulfill_store = options.get('store')
        fulfill_max = options.get('max')
        uptime = options.get('uptime')

        orders = ShopifyOrderTrack.objects.exclude(shopify_status='fulfilled') \
                                          .exclude(source_tracking='') \
                                          .exclude(hidden=True) \
                                          .filter(created_at__gte=arrow.now().replace(days=-30).datetime) \
                                          .filter(store__is_active=True) \
                                          .filter(store__auto_fulfill__in=['hourly', 'daily', 'enable']) \
                                          .defer('data') \
                                          .order_by('created_at')

        if fulfill_store is not None:
            orders = orders.filter(store=fulfill_store)

        fulfill_max = min(fulfill_max, len(orders)) if fulfill_max else len(orders)

        self.write('Auto Fulfill {}/{} Orders'.format(fulfill_max, len(orders)), self.style.HTTP_INFO)

        counter = {
            'fulfilled': 0,
            'need_fulfill': 0,
        }

        self.store_countdown = {}
        self.start_at = timezone.now()
        self.fulfill_threshold = timezone.now() - timezone.timedelta(seconds=threshold * 60)

        for order in orders[:fulfill_max]:
            try:
                counter['need_fulfill'] += 1

                if self.fulfill_order(order):
                    order.shopify_status = 'fulfilled'
                    order.auto_fulfilled = True
                    order.save()

                    counter['fulfilled'] += 1
                    if counter['fulfilled'] % 50 == 0:
                        self.write('Fulfill Progress: %d' % counter['fulfilled'])

                if (timezone.now() - self.start_at) > timezone.timedelta(seconds=uptime * 60):
                    raven_client.captureMessage(
                        'Auto fulfill taking too long',
                        level="warning",
                        extra={'delta': (timezone.now() - self.start_at).total_seconds()})

                    break
            except:
                raven_client.captureException()

        self.write('Fulfilled Orders: {} / {}'.format(
            counter['fulfilled'], counter['need_fulfill']))

    def fulfill_order(self, order):
        store = order.store
        user = store.user

        api_data = utils.order_track_fulfillment(order_track=order, user_config=user.get_config())

        fulfilled = False
        tries = 3

        while tries > 0:
            try:
                rep = requests.post(
                    url=store.get_link('/admin/orders/{}/fulfillments.json'.format(order.order_id), api=True),
                    json=api_data
                )

                rep.raise_for_status()

                fulfilled = 'fulfillment' in rep.json()
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
                    if 'is already fulfilled' in rep.text:
                        # Mark as fulfilled but not auto-fulfilled
                        self.write(u'Already fulfilled #{} in [{}]'.format(order.order_id, order.store.title))
                        order.shopify_status = 'fulfilled'
                        order.save()
                        return False

                    elif 'invalid for this fulfillment service' in rep.text:
                        # Using a different fulfillment_service (i.e: amazon_marketplace_web)
                        self.write(u'Invalid for this fulfillment service #{} in [{}]'.format(order.order_id, order.store.title))
                        order.shopify_status = 'fulfilled'
                        order.save()
                        return False

                elif e.response.status_code == 404:
                    self.write(u'Not found #{} in [{}]'.format(order.order_id, order.store.title))
                    order.delete()

                    return False

                elif e.response.status_code == 402:
                    order.hidden = True
                    order.save()

                    return False

                if "An error occurred, please try again" not in rep.text:
                    raven_client.captureException(extra={
                        'order_track': order.id,
                        'response': rep.text
                    })

            except:
                raven_client.captureException()
            finally:
                tries -= 1

        if fulfilled:
            note = "Auto Fulfilled by Dropified (Line Item #{})".format(order.line_id)

            countdown = self.store_countdown.get(store.id, 30)
            tasks.add_ordered_note.apply_async(args=[store.id, order.order_id, note], countdown=countdown)

            self.store_countdown[store.id] = countdown + 5

        return fulfilled
