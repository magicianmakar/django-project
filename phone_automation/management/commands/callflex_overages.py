from raven.contrib.django.raven_compat.models import client as raven_client

from phone_automation import billing_utils as billing
from shopified_core.management import DropifiedBaseCommand
# from phone_automation import utils as utils
from stripe_subscription.models import CustomStripeSubscription


class Command(DropifiedBaseCommand):
    help = 'Update Callflex Overages'

    def add_arguments(self, parser):
        parser.add_argument(
            '-u_id',
            '--user_id',
            default=False,
            help='Process only specified user'
        )

    def start_command(self, *args, **options):
        callflex_subscriptions = CustomStripeSubscription.objects.filter(custom_plan__type='callflex_subscription')
        if options['user_id']:
            callflex_subscriptions = callflex_subscriptions.filter(user_id=options['user_id'])

        for callflex_subscription in callflex_subscriptions.iterator():

            try:
                print(f"Processing subscrition {callflex_subscription.pk} (user_id: {callflex_subscription.user_id})")
                overages = billing.CallflexOveragesBilling(callflex_subscription.user)
                overages.update_overages()
            except:
                raven_client.captureException()
