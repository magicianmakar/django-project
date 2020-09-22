from lib.exceptions import capture_exception
from django.db.models import Sum
from phone_automation import billing_utils as billing
from shopified_core.management import DropifiedBaseCommand
# from phone_automation import utils as utils
from stripe_subscription.models import CustomStripeSubscription
from phone_automation.models import TwilioPhoneNumber, CallflexShopifyUsageCharge
from django.contrib.auth.models import User
from shopified_core.utils import last_executed
from datetime import datetime, timedelta
from django.conf import settings
from django.utils import timezone


class Command(DropifiedBaseCommand):
    help = 'Update Callflex Overages'

    def add_arguments(self, parser):
        parser.add_argument(
            '-u_id',
            '--user_id',
            default=False,
            help='Process only specified user'
        )

        parser.add_argument(
            '-shopify_force',
            '--shopify_force',
            default=False,
            help='Force running shopify daily usage (bypass cached) '
        )

    def start_command(self, *args, **options):

        # Get users without CallFlex Stripe Subscriptions
        users_phones = TwilioPhoneNumber.objects.exclude(status='released')
        if options['user_id']:
            users_phones = users_phones.filter(user_id=options['user_id'])
        users_phones = users_phones.values_list('user_id', flat=True)

        # Get users with CallFlex Stripe Subscriptions
        callflex_subscriptions = CustomStripeSubscription.objects.filter(custom_plan__type='callflex_subscription')
        if options['user_id']:
            callflex_subscriptions = callflex_subscriptions.filter(user_id=options['user_id'])

        users_subscriptions = callflex_subscriptions.values_list('user_id', flat=True)
        all_users_list = list(set(users_phones) | set(users_subscriptions))

        for user_id in all_users_list:
            user = User.objects.get(pk=user_id)
            try:
                overages = billing.CallflexOveragesBilling(user)
                if user.profile.from_shopify_app_store():
                    # run once a day only
                    today = datetime.now().strftime("%Y%m%d")
                    if options['shopify_force'] or not last_executed(f'callflex_shopify_usage_u_{user.id}_{today}', 3600 * 24):
                        overages.add_shopify_overages()
                else:
                    overages.update_overages()
            except:
                capture_exception()

        # Process users who have unpaid shopify usage
        unpaid_usage_charges = CallflexShopifyUsageCharge.objects
        if options['user_id']:
            unpaid_usage_charges = unpaid_usage_charges.filter(user_id=options['user_id'])

        unpaid_usage_charges_not_paid = unpaid_usage_charges.filter(status='not_paid').all()

        for unpaid_usage_charge in unpaid_usage_charges_not_paid:
            overages = billing.CallflexOveragesBilling(unpaid_usage_charge.user)
            try:
                charge_id = overages.add_shopify_usage_invoice(unpaid_usage_charge.type, unpaid_usage_charge.amount, True)
                if charge_id:
                    unpaid_usage_charge.status = "paid"
                    unpaid_usage_charge.save()
            except:
                capture_exception()
        # count how many unpaid usage charges are in queue
        unpaid_usage_charges_user = unpaid_usage_charges.filter(status='not_paid').values('user').\
            order_by('user').annotate(total_amount=Sum('amount'))
        for unpaid_user_total in unpaid_usage_charges_user:
            if unpaid_user_total['total_amount'] > settings.CALLFLEX_SHOPIFY_USAGE_MAX_PENDING:

                user = User.objects.get(pk=unpaid_user_total['user'])
                phones = user.twilio_phone_numbers.exclude(status='released')
                phones.safe_delete()

        # removing very old usage charge logs
        exp_date = timezone.now() + timedelta(days=-90)
        unpaid_usage_charges.filter(created_at__lte=exp_date).delete()
