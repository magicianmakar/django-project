from django.contrib.auth.models import User
from lib.exceptions import capture_exception
from shopified_core.commands import DropifiedBaseCommand
from stripe_subscription.stripe_api import stripe
from leadgalaxy.models import GroupPlan
from stripe_subscription.utils import update_subscription


class Command(DropifiedBaseCommand):
    help = 'Process 3-pay billing for lifetime customers (this command should run daily)'

    def add_arguments(self, parser):
        parser.add_argument(
            '-u_id',
            '--user_id',
            default=False,
            help='Process only specified user'
        )
        parser.add_argument(
            '-plan_id',
            '--plan_id',
            required=True,
            help='Process only this plan'
        )

    def start_command(self, *args, **options):
        users = User.objects.filter(profile__plan__id=options['plan_id'])

        if options['user_id']:
            users = users.filter(pk=options['user_id'])

        plan = GroupPlan.objects.get(pk=options['plan_id'])

        for user in users.iterator():
            current_stripe_sub = user.stripe_customer.current_subscription
            if not current_stripe_sub:

                try:
                    stripe_customer_data = user.stripe_customer.retrieve()
                    stripe_subscription_id = stripe_customer_data.subscriptions.data[0].id
                    sub = stripe.Subscription.retrieve(stripe_subscription_id)
                    update_subscription(user, plan, sub)
                    print(f'Updated user {user}')
                except IndexError:
                    print(f'Skip user {user} (no stripe sub)')
                except:
                    print(f'Skip user {user} (other error)')
                    capture_exception()
