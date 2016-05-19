from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth.models import User
from django.utils import timezone

import requests

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
        self.stdout.write(self.style.HTTP_INFO('* Archive seen alerts'))
        AliexpressProductChange.objects.filter(seen=True, hidden=False).update(hidden=True)

        # Expired plans
        self.stdout.write(self.style.HTTP_INFO('* Change plan of expired profiles'))
        for profile in UserProfile.objects.filter(plan_expire_at__lte=timezone.now()):
            if profile.plan_after_expire:
                print 'Changing:', profile
                self.profile_changed(profile, profile.plan, profile.plan_after_expire)

                profile.plan = profile.plan_after_expire
                profile.plan_after_expire = None
                profile.plan_expire_at = None
                profile.save()

        # Auto fulfill (Daily)
        time_threshold = timezone.now() - timezone.timedelta(days=1)
        orders = ShopifyOrderTrack.objects.exclude(shopify_status='fulfilled').exclude(source_tracking='') \
                                     .filter(status_updated_at__lt=time_threshold) \
                                     .order_by('store', 'status_updated_at')

        print 'Orders Count (daily):', orders.count()

        users = {}
        count = 0
        self.store_countdown = {}

        for order in orders:
            if order.store_id in users:
                user = users[order.store_id]
            else:
                user = order.store.user

            if not user or user.get_config('auto_shopify_fulfill') != 'daily':
                users[order.store_id] = False
                continue
            else:
                users[order.store_id] = user

            try:
                if self.fulfill_order(order, order.store, user):
                    order.shopify_status = 'fulfilled'
                    order.auto_fulfilled = True
                    order.save()

                    count += 1
                    if count % 50 == 0:
                        print 'Fulfill Progress: %d' % count

            except:
                raven_client.captureException()

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
        api_data = utils.order_track_fulfillment(order)

        if user.get_config('validate_tracking_number', True) and \
                not utils.is_valide_tracking_number(order.source_tracking):
            notify_customer = 'no'
        else:
            notify_customer = user.get_config('send_shipping_confirmation', 'default')

        if notify_customer and notify_customer != 'default':
            api_data['fulfillment']['notify_customer'] = (notify_customer == 'yes')

        rep = requests.post(
            url=store.get_link('/admin/orders/{}/fulfillments.json'.format(order.order_id), api=True),
            json=api_data
        )

        fulfilled = 'fulfillment' in rep.json()
        if fulfilled:
            note = "Auto Fulfilled by Shopified App (Line Item #{})".format(order.line_id)

            countdown = self.store_countdown.get(store.id, 30)
            tasks.add_ordered_note.apply_async(args=[store.id, order.order_id, note], countdown=countdown)

            self.store_countdown[store.id] = countdown + 5

        return fulfilled
