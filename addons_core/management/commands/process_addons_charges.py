import argparse

import arrow
from django.db.models import F, Prefetch
from django.contrib.auth.models import User

from lib.exceptions import capture_exception
from shopified_core.management import DropifiedBaseCommand
from addons_core.models import AddonUsage
from addons_core.utils import get_stripe_subscription, add_stripe_subscription_item, charge_stripe_first_time


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
        users = User.objects.exclude(
            addonusage__billed_to__gte=F('addonusage__cancelled_at'),
            addonusage__cancelled_at__isnull=False,
        ).distinct()
        addon_usages = AddonUsage.objects.exclude(
            billed_to__gte=F('cancelled_at'),
            cancelled_at__isnull=False,
        )

        if options['today'].ceil('month').day == options['today'].day:
            # Some months have lesser days
            addon_usages = addon_usages.filter(interval_day__gte=options['today'].day)
            users = users.filter(addonusage__interval_day__gte=options['today'].day)
        else:
            addon_usages = addon_usages.filter(interval_day=options['today'].day)
            users = users.filter(addonusage__interval_day=options['today'].day)

        # Process only subscribed addons. Search must be equal for "user.addonusages"
        users = users.prefetch_related(Prefetch('addonusage_set', addon_usages, to_attr='addon_usages'))
        if options['user_id']:
            users = users.filter(id=options['user_id'])

        for user in users.all():
            if user.is_stripe_customer():
                stripe_subscription = get_stripe_subscription(user)

                for addon_usage in user.addon_usages:
                    first_payment = addon_usage.billed_to is None
                    try:
                        start, end, latest_charge = addon_usage.get_latest_charge(today_date=options['today'], save=False)
                        # Negative charge can be due prorated cancellation after billing day
                        if latest_charge <= 0:
                            continue

                        if first_payment:
                            added = charge_stripe_first_time(addon_usage)
                        else:
                            added = add_stripe_subscription_item(
                                stripe_subscription=stripe_subscription,
                                amount=latest_charge,
                                addon_usage=addon_usage,
                                period={
                                    "end": end.floor('day').timestamp,
                                    "start": start.floor('day').timestamp,
                                },
                            )

                        if added:
                            addon_usage.save()

                    except:
                        capture_exception()

            elif user.profile.from_shopify_app_store():
                # TODO shopify billing can be here (using usage charge api)
                pass
