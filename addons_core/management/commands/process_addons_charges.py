import argparse

import arrow
from django.db.models import Q, Prefetch
from django.contrib.auth.models import User

from lib.exceptions import capture_exception
from shopified_core.management import DropifiedBaseCommand
from addons_core.models import AddonUsage
from addons_core.utils import (
    create_stripe_subscription,
    update_stripe_subscription,
    remove_cancelled_addons,
)


class Command(DropifiedBaseCommand):
    help = 'Process Pending Sales Fees'

    def add_arguments(self, parser):
        parser.add_argument(
            '-u_id',
            '--user_id',
            default=False,
            help='Process only specified user'
        )

        def arrow_date(input_value):
            today = arrow.get(input_value, 'YYYY-MM-DD')
            if today.format('YYYY-MM-DD') != input_value:
                raise argparse.ArgumentTypeError(
                    f"Wrong date format (YYYY-MM-DD): {today.format('YYYY-MM-DD')} != {input_value}")
            return today
        parser.add_argument('today', nargs='?', type=arrow_date, default=arrow.get())

    def start_command(self, *args, **options):
        today = options['today'].date()
        today_begin = options['today'].floor('day').datetime
        today_end = options['today'].ceil('day').datetime
        prev_day = options['today'].shift(days=-1).date()

        # Addons that change prices between months in stripe will make that change
        # before upcomming invoice is create
        users = User.objects.filter(
            Q(addonusage__cancel_at__range=(today_begin, today_end))
            | (Q(addonusage__cancelled_at__isnull=True)
               & Q(addonusage__next_billing__range=(prev_day, today)))
        ).distinct()
        addon_usages = AddonUsage.objects.filter(
            next_billing__range=(prev_day, today),
            cancelled_at__isnull=True,
        )
        cancelled_usages = AddonUsage.objects.filter(cancelled_at__range=(today_begin, today_end))

        users = users.prefetch_related(
            Prefetch('addonusage_set', addon_usages, to_attr='addon_subscriptions'),
            Prefetch('addonusage_set', cancelled_usages, to_attr='cancelled_subscriptions'),
        )
        if options['user_id']:
            users = users.filter(id=options['user_id'])

        for user in users.all():
            if user.is_stripe_customer():
                for addon_usage in user.addon_subscriptions:
                    try:
                        if not addon_usage.stripe_subscription_item_id:
                            subscription_item = create_stripe_subscription(addon_usage)

                        else:
                            subscription_item = update_stripe_subscription(addon_usage)

                        if subscription_item is None:
                            raise Exception(f'<AddonUsage: {addon_usage.id}> without subscription')

                        addon_usage.next_billing = addon_usage.get_next_billing_date()
                        addon_usage.save()
                    except:
                        capture_exception()

            elif user.profile.from_shopify_app_store():
                # TODO shopify billing can be here (using usage charge api)
                pass

            remove_cancelled_addons(user.cancelled_subscriptions)
