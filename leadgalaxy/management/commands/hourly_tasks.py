from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth.models import User
from django.utils import timezone

import requests
import time
from simplejson import JSONDecodeError

from leadgalaxy.models import *
from leadgalaxy import utils
from leadgalaxy import tasks

from raven.contrib.django.raven_compat.models import client as raven_client


class Command(BaseCommand):
    def add_arguments(self, parser):
        pass

    def handle(self, *args, **options):
        try:
            self.start_command(*args, **options)
        except:
            raven_client.captureException()

    def start_command(self, *args, **options):
        # TODO: Repeated code
        # TODO: Filter hidden=True
        # Auto fulfill (Hourly)
        time_threshold = timezone.now() - timezone.timedelta(hours=1)
        orders = ShopifyOrderTrack.objects.exclude(shopify_status='fulfilled').exclude(source_tracking='') \
                                          .filter(status_updated_at__lt=time_threshold) \
                                          .order_by('store', 'status_updated_at')

        print 'Orders Count (hourly):', orders.count()

        users = {}
        counter = {
            'fulfilled': 0,
            'need_fulfill': 0,
            'ignored_orders': 0,
        }

        self.store_countdown = {}

        for order in orders:
            if order.store_id in users:
                user = users[order.store_id]
            else:
                user = order.store.user

            fulfill_option = user.get_config('auto_shopify_fulfill') if user else None
            if not user or fulfill_option != 'hourly':
                users[order.store_id] = False
                counter['ignored_orders'] += 1
                continue
            else:
                users[order.store_id] = user

            try:
                counter['need_fulfill'] += 1

                if self.fulfill_order(order, order.store, user):
                    order.shopify_status = 'fulfilled'
                    order.auto_fulfilled = True
                    order.save()

                    counter['fulfilled'] += 1
                    if counter['fulfilled'] % 50 == 0:
                        print 'Fulfill Progress: %d' % counter['fulfilled']

            except:
                raven_client.captureException()

        print 'Fulfilled Orders:', counter['fulfilled']
        print 'Need Fulfill Orders:', counter['need_fulfill']
        print 'Ignored Orders:', counter['ignored_orders']

    def profile_changed(self, profile, expired_plan, new_plan):
        data = {
            'profile': profile,
            'expired_plan': expired_plan,
            'new_plan': new_plan
        }

        utils.send_email_from_template(tpl='expire_plan_change.html',
                                       subject='[Shopified App] Plan Expire',
                                       recipient=['ma7dev@gmail.com', 'chase@shopifiedapp.com'],
                                       data=data,
                                       nl2br=False)

    def fulfill_order(self, order, store, user):
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
                print 'Sleep For 2 sec'
                time.sleep(2)
                continue
            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 429:
                    # Wait and retry
                    print 'Sleep For 5 sec'
                    time.sleep(5)
                    continue

                elif e.response.status_code == 422:
                    if 'is already fulfilled' in rep.text:
                        # Mark as fulfilled but not auto-fulfilled
                        print 'Already fulfilled #{} in [{}]'.format(order.order_id, order.store.title)
                        order.shopify_status = 'fulfilled'
                        order.save()
                        return False

                elif e.response.status_code == 404:
                    print 'Not found #{} in [{}]'.format(order.order_id, order.store.title)
                    order.delete()

                    return False

                raven_client.captureException()

            except:
                raven_client.captureException()
            finally:
                tries -= 1

        if fulfilled:
            note = "Auto Fulfilled by Shopified App (Line Item #{})".format(order.line_id)

            countdown = self.store_countdown.get(store.id, 30)
            tasks.add_ordered_note.apply_async(args=[store.id, order.order_id, note], countdown=countdown)

            self.store_countdown[store.id] = countdown + 5
        else:
            raven_client.captureMessage('Order Was not fulfilled', extra={'order': order.id}, level='warning')

        return fulfilled
