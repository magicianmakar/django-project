from django.utils import timezone

import requests
import time
from simplejson import JSONDecodeError
from tqdm import tqdm

from shopified_core.management import DropifiedBaseCommand
from leadgalaxy.models import *
from shopify_orders.models import ShopifyOrderLog
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

        parser.add_argument('--progress', dest='progress', action='store_true', help='Shopw Reset Progress')

    def start_command(self, *args, **options):
        fulfill_store = options.get('store')
        fulfill_max = options.get('max')
        uptime = options.get('uptime')

        orders = ShopifyOrderTrack.objects.filter(shopify_status='') \
                                          .exclude(source_tracking='') \
                                          .filter(hidden=False) \
                                          .filter(created_at__gte=arrow.now().replace(days=-30).datetime) \
                                          .filter(store__is_active=True) \
                                          .filter(store__auto_fulfill='enable') \
                                          .defer('data') \
                                          .order_by('created_at')

        if fulfill_store is not None:
            orders = orders.filter(store=fulfill_store)

        self.write('Start Auto Fulfill')

        if options['progress']:
            pbar = tqdm(total=orders.count())

        counter = {
            'fulfilled': 0,
            'need_fulfill': 0,
        }

        self.store_countdown = {}
        self.store_locations = {}
        self.start_at = timezone.now()

        for order in orders[:fulfill_max]:
            if options['progress']:
                pbar.update(1)

            try:
                counter['need_fulfill'] += 1

                if self.fulfill_order(order):
                    order.shopify_status = 'fulfilled'
                    order.auto_fulfilled = True
                    order.save()

                    counter['fulfilled'] += 1
                    if not options['progress'] and counter['fulfilled'] % 50 == 0:
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

        api_data, line = utils.order_track_fulfillment(
            order_track=order,
            user_config=user.get_config(),
            return_line=True,
            location_id=self.store_locations.get(order.store.id))

        locations = []
        fulfilled = False
        tries = 3

        while tries > 0 or locations:
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

                        self.log_fulfill_error(order, 'Order is already fulfilled')

                        return False

                    elif 'This order has been canceled' in rep.text:
                        self.write(u'Order has been canceled #{} in [{}]'.format(order.order_id, order.store.title))
                        order.hidden = True
                        order.save()

                        self.log_fulfill_error(order, 'This order has been canceled')

                        return False

                    elif 'invalid for this fulfillment service' in rep.text:
                        # Using a different fulfillment_service (i.e: amazon_marketplace_web)
                        self.write(u'Invalid for this fulfillment service #{} in [{}]'.format(order.order_id, order.store.title))
                        order.shopify_status = 'fulfilled'
                        order.save()

                        self.log_fulfill_error(order, 'Invalid for this fulfillment service')

                        return False

                    elif 'must be stocked at the same location' in rep.text:
                        if locations:
                            # We are trying locations one by one
                            location = locations.pop()
                            self.write(u'Re-trying location {} for #{} in {}'.format(location['id'], order.order_id, order.store.shop))
                        else:
                            # Try locations one by one
                            locations = store.get_locations()
                            location = locations.pop()
                            self.write(u'Trying location {} for #{} in {}'.format(location['id'], order.order_id, order.store.shop))

                        if location:
                            api_data["fulfillment"]["location_id"] = location['id']

                            self.store_locations[order.store.id] = location['id']
                            self.write(u'Change location to {} in #{} [{}]'.format(location['name'], order.order_id, order.store.shop))

                            self.log_fulfill_error(order, u'Fulfill in location: {}'.format(location['name']), shopify_api=False)

                        else:
                            raven_client.captureMessage(u'No location found', extra={'track': order.id, 'store': order.store.shop})

                            self.log_fulfill_error(order, 'No location found', shopify_api=False)

                            order.hidden = True
                            order.save()

                        continue

                elif e.response.status_code == 404:
                    raven_client.captureException(extra={
                        'order_track': order.id,
                        'response': rep.text
                    })

                    self.log_fulfill_error(order, 'Order Not Found')

                    self.write(u'Not found #{} in [{}]'.format(order.order_id, order.store.title))
                    order.hidden = True
                    order.save()

                    return False

                elif e.response.status_code in [401, 402, 403]:
                    self.log_fulfill_error(order, 'API Authorization ({})'.format(e.response.status_code))

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
            msg = u'Shopify API Error: {}'.format(msg)

        ShopifyOrderLog.objects.update_order_log(
            store=order.store,
            user=None,
            log=msg,
            level='error',
            icon='times',
            order_id=order.order_id,
            line_id=order.line_id
        )
