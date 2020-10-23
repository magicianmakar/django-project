import argparse

import arrow
from django.db.models import Prefetch
from django.contrib.auth.models import User

from lib.exceptions import capture_exception
from shopified_core.management import DropifiedBaseCommand
from addons_core.models import AddonUsage
from addons_core.utils import create_stripe_subscription, update_stripe_subscription


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
        prev_day = options['today'].shift(days=-1).date()

        # Addons that change prices between months in stripe will make that change
        # before upcomming invoice is create
        users = User.objects.filter(
            addonusage__next_billing__range=(prev_day, today),
            addonusage__cancelled_at__isnull=True,
        ).distinct()
        addon_usages = AddonUsage.objects.filter(
            next_billing__range=(prev_day, today),
            cancelled_at__isnull=True,
        )

        users = users.prefetch_related(Prefetch('addonusage_set', addon_usages, to_attr='addon_subscriptions'))
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

                    except:
                        capture_exception()

            elif user.profile.from_shopify_app_store():
                # TODO shopify billing can be here (using usage charge api)
                pass
