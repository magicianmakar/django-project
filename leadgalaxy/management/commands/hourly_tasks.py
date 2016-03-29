from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth.models import User
from django.utils import timezone

import requests
import traceback
from simplejson import JSONDecodeError

from leadgalaxy.models import *
from leadgalaxy import utils


class Command(BaseCommand):
    def add_arguments(self, parser):
        pass

    def handle(self, *args, **options):
        # TODO: Repeated code
        # Auto fulfill (Hourly)
        time_threshold = timezone.now() - timezone.timedelta(hours=1)
        orders = ShopifyOrder.objects.exclude(shopify_status='fulfilled').exclude(source_tracking='') \
                                     .filter(status_updated_at__lt=time_threshold) \
                                     .order_by('store', 'status_updated_at')

        print 'Orders Count (hourly):', orders.count()

        users = {}
        count = 0
        for order in orders:
            if order.store_id in users:
                user = users[order.store_id]
            else:
                user = order.store.user

            if not user or user.get_config('auto_shopify_fulfill') != 'hourly':
                users[order.store_id] = False
                continue
                pass
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

            except JSONDecodeError:
                print 'ERROR: JSON DECODE ERROR'
            except:
                print 'ERROR: Fulfill Exception:'
                traceback.print_exc()

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
        tracking = order.source_tracking

        api_data = {
            "fulfillment": {
                "tracking_number": tracking,
                "tracking_company": "Other",
                "tracking_url": "https://track.aftership.com/{}".format(tracking),
                "line_items": [{
                    "id": order.line_id,
                    # "quantity": int(data.get('fulfill-quantity'))
                }]
            }
        }

        if user.get_config('validate_tracking_number', True) and re.match('^[0-9]+$', tracking):
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
            try:
                utils.add_shopify_order_note(store, order.order_id, note)
            except Exception as e:
                print '- Add Note Exception:', e

        return fulfilled
