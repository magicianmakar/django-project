import argparse

import arrow
from django.db.models import Q, Prefetch
from django.contrib.auth.models import User
from django.urls import reverse

from lib.exceptions import capture_exception
from shopified_core.management import DropifiedBaseCommand
from shopified_core.utils import app_link, send_email_from_template
from addons_core.models import AddonUsage
from addons_core.utils import (
    create_stripe_subscription,
    update_stripe_subscription,
    remove_cancelled_addons,
    has_shopify_limit_exceeded,
    create_shopify_charge,
    cancel_addon_usages,
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
        today_range = (options['today'].floor('day').datetime,
                       options['today'].ceil('day').datetime)
        prev_day = options['today'].shift(days=-1).date()
        next_day = options['today'].shift(days=1).date()
        seven_days_ago = options['today'].shift(days=-7).date()

        for missed_usage_charge in AddonUsage.objects.filter(
                next_billing__lt=arrow.get(today).shift(months=-2).datetime,
                cancelled_at__isnull=True):
            missed_usage_charge.next_billing = missed_usage_charge.get_next_billing_date(today)
            missed_usage_charge.save()

        # Addons that change prices between months in stripe need to make that
        # change before upcomming invoice is created
        users = User.objects.filter(
            Q(addonusage__cancel_at__range=today_range)
            | (Q(addonusage__next_billing__range=(seven_days_ago, next_day))
               & Q(addonusage__cancelled_at__isnull=True))
        ).distinct()
        usages = AddonUsage.objects.filter(
            next_billing__range=(today, next_day),
            cancelled_at__isnull=True,
        )
        overdue_usages = AddonUsage.objects.filter(
            next_billing__range=(seven_days_ago, prev_day),
            cancelled_at__isnull=True,
        )
        cancelled_usages = AddonUsage.objects.filter(
            cancel_at__range=today_range
        )
        users = users.prefetch_related(
            Prefetch('addonusage_set', usages, to_attr='addon_subscriptions'),
            Prefetch('addonusage_set', overdue_usages, to_attr='overdue_subscriptions'),
            Prefetch('addonusage_set', cancelled_usages, to_attr='cancelled_subscriptions'),
        )

        if options['user_id']:
            users = users.filter(id=options['user_id'])

        for user in users.all():
            if user.is_stripe_customer():
                for addon_usage in user.addon_subscriptions:
                    try:
                        if not addon_usage.stripe_subscription_item_id:
                            subscription_item = create_stripe_subscription(addon_usage, today=today)

                        else:
                            subscription_item = update_stripe_subscription(addon_usage, today=today)

                        if subscription_item is None and addon_usage.next_billing == today:
                            raise Exception(f'<AddonUsage: {addon_usage.id}> without subscription')

                        addon_usage.next_billing = addon_usage.get_next_billing_date(today=today)
                        addon_usage.save()
                    except:
                        capture_exception()

            elif user.profile.from_shopify_app_store():
                limit_exceeded = has_shopify_limit_exceeded(user, today=today)
                if limit_exceeded:
                    # Cancel addons overdue for 7 days
                    addon_usages = []
                    for addon_usage in user.overdue_subscriptions:
                        if addon_usage.next_billing > seven_days_ago:
                            continue

                        addon_usages.append(addon_usage)

                    cancel_addon_usages(addon_usages, now=True)
                    send_email_from_template(
                        tpl='shopify_capped_limit_warning.html',
                        subject='Dropified Subscription - action required',
                        recipient=user.email,
                        data={
                            'profile_link': app_link(reverse('user_profile')),
                            'new_limit_confirmation_link': limit_exceeded,
                            'addon_usages': addon_usages
                        }
                    )
                    continue

                # TODO: create shopify subscription for yearly plans
                for addon_usage in user.addon_subscriptions:
                    # Add charges at the right time for shopify
                    if addon_usage.next_billing != today:
                        continue

                    try:
                        create_shopify_charge(addon_usage, today=today)
                    except:
                        capture_exception()

                # Attempt to create charge for overdue charges
                for addon_usage in user.overdue_subscriptions:
                    try:
                        create_shopify_charge(addon_usage, today=today)
                    except:
                        capture_exception()

            remove_cancelled_addons(user.cancelled_subscriptions)
