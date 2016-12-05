from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth.models import User
from django.utils import timezone

import requests
import time
import arrow
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
        # Archive seen changes
        self.stdout.write('Archive seen alerts', self.style.HTTP_INFO)
        AliexpressProductChange.objects.filter(seen=True, hidden=False).update(hidden=True)

        # Archive alerts after 7 days
        archive_date = arrow.utcnow().replace(days=-7).datetime
        AliexpressProductChange.objects.filter(hidden=False, created_at__lt=archive_date).update(hidden=True)

        # Remove alerts after 30 days
        delete_date = arrow.utcnow().replace(days=-30).datetime
        AliexpressProductChange.objects.filter(created_at__lt=delete_date).update(hidden=True)

        # Expired plans
        self.stdout.write('Change plan of expired profiles', self.style.HTTP_INFO)
        for profile in UserProfile.objects.filter(plan_expire_at__lte=timezone.now()):
            if profile.plan_after_expire:
                self.stdout.write(u'Changing: {}'.format(profile.user.username))
                self.profile_changed(profile, profile.plan, profile.plan_after_expire)

                profile.plan = profile.plan_after_expire
                profile.plan_after_expire = None
                profile.plan_expire_at = None
                profile.save()

        # Invoice Extra Stores
        from stripe_subscription.utils import invoice_extra_stores
        invoice_extra_stores()

        # Auto fulfill (Daily)
        time_threshold = timezone.now() - timezone.timedelta(days=1)
        orders = ShopifyOrderTrack.objects.exclude(shopify_status='fulfilled').exclude(source_tracking='') \
                                          .filter(status_updated_at__lt=time_threshold) \
                                          .exclude(hidden=True) \
                                          .filter(store__auto_fulfill='daily') \
                                          .filter(store__is_active=True) \
                                          .order_by('store', 'status_updated_at')

        self.stdout.write('Orders Count (daily): %d' % orders.count(), self.style.HTTP_INFO)

        counter = {
            'fulfilled': 0,
            'need_fulfill': 0,
        }

        self.store_countdown = {}

        for order in orders:
            try:
                counter['need_fulfill'] += 1

                if self.fulfill_order(order, order.store, order.store.user):
                    order.shopify_status = 'fulfilled'
                    order.auto_fulfilled = True
                    order.save()

                    counter['fulfilled'] += 1
                    if counter['fulfilled'] % 50 == 0:
                        self.stdout.write('Fulfill Progress: %d' % counter['fulfilled'])

            except:
                raven_client.captureException()

        self.stdout.write('Fulfilled Orders: {} / {}'.format(
            counter['fulfilled'], counter['need_fulfill']))

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
                self.stdout.write('Sleep for 2 sec')
                time.sleep(2)
                continue
            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 429:
                    # Wait and retry
                    self.stdout.write('Sleep for 5 sec')
                    time.sleep(5)
                    continue

                elif e.response.status_code == 422:
                    if 'is already fulfilled' in rep.text:
                        # Mark as fulfilled but not auto-fulfilled
                        self.stdout.write(u'Already fulfilled #{} in [{}]'.format(order.order_id, order.store.title))
                        order.shopify_status = 'fulfilled'
                        order.save()
                        return False

                    elif 'invalid for this fulfillment service' in rep.text:
                        # Using a different fulfillment_service (i.e: amazon_marketplace_web)
                        self.stdout.write(u'Invalid for this fulfillment service #{} in [{}]'.format(order.order_id, order.store.title))
                        order.shopify_status = 'fulfilled'
                        order.save()
                        return False

                elif e.response.status_code == 404:
                    self.stdout.write(u'Not found #{} in [{}]'.format(order.order_id, order.store.title))
                    order.delete()

                    return False

                elif e.response.status_code == 402:
                    order.hidden = True
                    order.save()

                    return False

                raven_client.captureException(extra={'order_track': order.id, 'response': rep.text})

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
