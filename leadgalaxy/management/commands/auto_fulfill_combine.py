import re

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

        fulfill_max = min(fulfill_max, len(orders)) if fulfill_max else len(orders)

        self.write('Auto Fulfill {}/{} Orders'.format(fulfill_max, len(orders)), self.style.HTTP_INFO)

        counter = {
            'fulfilled': 0,
            'need_fulfill': 0,
        }

        self.store_countdown = {}
        self.start_at = timezone.now()

        self.trackings = {}
        self.check_orders_line_id = {}

        for order in orders:
            # Base dict with data needed for fulfillments
            data = {
                'api': {},
                'line_items': [],
                'line_item_ids': [order.line_id],
                'orders': [order],
                'run': False,  # For checking if it was already sent
            }
            key = '{}-{}-{}'.format(order.store_id, order.order_id, order.source_tracking)
            if key in self.trackings:  # Update data
                data = self.trackings[key]
                data['orders'].append(order)
                data['line_item_ids'].append(order.line_id)

            self.trackings[key] = self.get_fulfillment_data(order, data)

        for order in orders[:fulfill_max]:
            key = '{}-{}-{}'.format(order.store_id, order.order_id, order.source_tracking)
            if self.trackings[key]['run'] is True:
                continue

            try:
                count_orders = len(self.trackings[key]['orders'])
                counter['need_fulfill'] += count_orders

                if self.fulfill_order(self.trackings[key]):
                    for i in self.trackings[key]['orders']:
                        i.shopify_status = 'fulfilled'
                        i.auto_fulfilled = True
                        i.save()

                    counter['fulfilled'] += count_orders
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

    def get_fulfillment_data(self, order, data):
        api_data, line = utils.order_track_fulfillment(order_track=order, user_config=order.store.user.get_config(), return_line=True)
        data['line_items'].append(line)

        if 'fulfillment' in data['api']:
            data['api']['fulfillment']['line_items'] += api_data['fulfillment']['line_items']
        else:
            data['api'] = api_data

        return data

    def fulfill_order(self, data):
        first_order = data['orders'][0]
        store = first_order.store
        fulfilled = False
        tries = 3

        while tries > 0:
            try:
                rep = requests.post(
                    url=store.get_link('/admin/orders/{}/fulfillments.json'.format(first_order.order_id), api=True),
                    json=data['api']
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
                        self.write(u'Already fulfilled #{} in [{}]'.format(first_order.order_id, store.title))
                        data['api'], fulfilled_line_ids = self.fix_api_line_items(first_order, data['api'], rep.json()['errors']['base'])
                        for order in data['orders']:
                            if order.line_id in fulfilled_line_ids:
                                order.shopify_status = 'fulfilled'
                                order.save()

                        tries = 3
                        if len(data['api']['fulfillment']['line_items']) > 0:
                            continue
                        else:
                            return False

                    elif 'invalid for this fulfillment service' in rep.text:
                        # Using a different fulfillment_service (i.e: amazon_marketplace_web)
                        self.write(u'Invalid for this fulfillment service #{} in [{}]'.format(first_order.order_id, store.title))
                        for order in data['orders']:
                            order.shopify_status = 'fulfilled'
                            order.save()
                        return False

                elif e.response.status_code == 404:
                    self.write(u'Not found #{} in [{}]'.format(first_order.order_id, store.title))
                    for order in data['orders']:
                        order.delete()

                    return False

                elif e.response.status_code == 402:
                    for order in data['orders']:
                        order.hidden = True
                        order.save()

                    return False

                if "An error occurred, please try again" not in rep.text:
                    raven_client.captureException(extra={
                        'order_track': first_order.id,
                        'response': rep.text
                    })

            except:
                raven_client.captureException()
            finally:
                tries -= 1

        if fulfilled:
            data['run'] = True
            if store.user.get_config('aliexpress_as_notes', True):
                note = "Auto Fulfilled by Dropified (Items: {})".format(", ".join([str(j) for j in data['line_item_ids']]))

                countdown = self.store_countdown.get(store.id, 30)
                tasks.add_ordered_note.apply_async(args=[store.id, first_order.order_id, note], countdown=countdown)

                self.store_countdown[store.id] = countdown + 5

            for i in data['line_items']:
                i.fulfillment_status = 'fulfilled'
                i.save()

        return fulfilled

    def fix_api_line_items(self, order_track, api_data, errors):
        url = order_track.store.get_link('/admin/orders.json?ids={}'.format(order_track.order_id), api=True)
        response = requests.get(url=url)

        # Errors only show the title of the line item
        titles = []
        for error in errors:
            found = re.search(r"\'(.+)\'", error)
            if found is not None:
                titles.append(found.group()[1:-1])
        fulfilled_line_ids = []

        order = response.json()['orders'][0]
        for line_item in order['line_items']:
            if line_item['title'] in titles:
                for i in range(len(api_data['fulfillment']['line_items'])):
                    if api_data['fulfillment']['line_items'][i]['id'] == line_item['id']:
                        api_data['fulfillment']['line_items'].pop(i)
                        fulfilled_line_ids.append(line_item['id'])

        return api_data, fulfilled_line_ids
