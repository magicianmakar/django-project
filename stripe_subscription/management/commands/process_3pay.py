from django.contrib.auth.models import User
from lib.exceptions import capture_exception
from shopified_core.commands import DropifiedBaseCommand
from stripe_subscription.stripe_api import stripe
import datetime
from django.conf import settings


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

        for user in users.iterator():
            stripe_customer = user.stripe_customer
            current_stripe_sub = stripe_customer.current_subscription

            for product_to_process in settings.LIFETIME3PAY_PRODUCTS:
                try:
                    self.write(f"Processing User ID:{user.pk} [ {product_to_process['title']} ] ")

                    # skip user if 3 charges already done or not found any
                    tracked_charges = user.profile.get_config_value(f'{product_to_process["config_prefix"]}-charges', False)
                    if not tracked_charges or tracked_charges >= product_to_process['charges']:
                        print("Skip this")
                        continue

                    # fetch latest stripe sub data
                    stripe_subscription = user.stripesubscription_set.get(subscription_id=current_stripe_sub['id'])
                    stripe_subscription.refresh()

                    # check if today is the last subscription day and need to add invoice item for multi-pay product
                    close_to_renewal = stripe_subscription.period_end.timestamp() - datetime.datetime.now().timestamp() <= 86400

                    # check if far from last charge\invoice date (to prevent duplicating script runs)
                    lastcharge_timestamp = user.profile.get_config_value(f'{product_to_process["config_prefix"]}-lastcharge-timestamp', False)
                    lastcharge_amount = user.profile.get_config_value(f'{product_to_process["config_prefix"]}-amount', False)
                    far_from_last_charge = datetime.datetime.now().timestamp() - lastcharge_timestamp >= (86400 * 15)  # more than 15 days passed

                    print(f'close_to_renewal: {close_to_renewal}')
                    print(f'far_from_last_charge: {far_from_last_charge}')

                    # DEBUG
                    # close_to_renewal = True
                    # far_from_last_charge = True

                    if stripe_subscription.is_active and tracked_charges < product_to_process['charges'] \
                            and close_to_renewal and far_from_last_charge:
                        # adding invoice item
                        try:
                            upcoming_invoice_item = stripe.InvoiceItem.create(
                                customer=stripe_customer.customer_id,
                                amount=lastcharge_amount,
                                currency="USD",
                                description=product_to_process['title']
                            )
                            if upcoming_invoice_item:
                                # update last charge date
                                user.profile.set_config_value(f'{product_to_process["config_prefix"]}-charges',
                                                              tracked_charges + 1)
                                user.profile.set_config_value(f'{product_to_process["config_prefix"]}-lastcharge-timestamp',
                                                              datetime.datetime.now().timestamp())
                        except:
                            capture_exception()

                except:
                    capture_exception()
