from django.contrib.auth.models import User
from lib.exceptions import capture_exception
from shopified_core.commands import DropifiedBaseCommand
from stripe_subscription.stripe_api import stripe
from django.conf import settings


class Command(DropifiedBaseCommand):
    help = 'Detect 3-pay charges for Lifetime custobers (this commands runs only once, to process customers \
        which didn\'t have config set during webhook)'

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

        for user in users.iterator():
            stripe_customer = user.stripe_customer

            for product_to_process in settings.LIFETIME3PAY_PRODUCTS:
                try:
                    self.write(f"Processing User ID:{user.pk} [ {product_to_process['title']} ] ")

                    # skip user if 3 charges already done or not found any
                    tracked_charges = user.profile.get_config_value(f'{product_to_process["config_prefix"]}-charges', False)
                    if tracked_charges >= product_to_process['charges'] or (tracked_charges == 0 and tracked_charges is not False):
                        print("Skip this")
                        continue

                    if not user.profile.bundles.filter(slug='retro-elite-lifetime').exists() and \
                            not user.profile.bundles.filter(slug='retro-unlimited-pass').exists():
                        print("Skip this (bundles not found)")
                        continue

                    # fetching all 3-pay charges to detect 3-pay product, update data in user's profile config
                    charges = stripe.Charge.list(limit=30, customer=stripe_customer.customer_id).data
                    count_charges = 0
                    first_multicharge = None
                    for charge in charges:
                        if charge.paid and not charge.refunded and product_to_process["title"] in charge.description.lower():
                            print(charge.description.lower())
                            first_multicharge = charge
                            count_charges = count_charges + 1
                            lastcharge_timestamp = user.profile.get_config_value(f'{product_to_process["config_prefix"]}-lastcharge-timestamp', False)

                            # update last charge timestamp in user's profile for future use
                            if not lastcharge_timestamp or lastcharge_timestamp <= charge.created:
                                user.profile.set_config_value(f'{product_to_process["config_prefix"]}-lastcharge-timestamp', charge.created)
                                user.profile.set_config_value(f'{product_to_process["config_prefix"]}-amount', first_multicharge.amount)
                    user.profile.set_config_value(f'{product_to_process["config_prefix"]}-charges', count_charges)

                except:
                    capture_exception()
