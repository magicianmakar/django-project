from lib.exceptions import capture_exception
from shopified_core.management import DropifiedBaseCommand
from fulfilment_fee.models import SaleTransactionFee
from stripe_subscription.utils import add_invoice
from shopify_subscription.utils import add_shopify_usage_invoice
from stripe_subscription.stripe_api import stripe
from stripe_subscription.models import CustomStripePlan, CustomStripeSubscription
import arrow
import simplejson as json


class Command(DropifiedBaseCommand):
    help = 'Process Pending Sales Fees'

    def add_arguments(self, parser):
        parser.add_argument(
            '-u_id',
            '--user_id',
            default=False,
            help='Process only specified user'
        )

    def start_command(self, *args, **options):
        sale_transaction_fees = SaleTransactionFee.objects.filter(processed=False)
        if options['user_id']:
            sale_transaction_fees = sale_transaction_fees.filter(user_id=options['user_id'])
        sale_transaction_fees = sale_transaction_fees.all()

        skip_user_ids = []
        for sale_transaction_fee in sale_transaction_fees:
            try:
                if sale_transaction_fee.user.is_stripe_customer() and sale_transaction_fee.user.id not in skip_user_ids:
                    try:
                        # getting Stripe subscription container
                        user_transactionfee_subscription = sale_transaction_fee.user.customstripesubscription_set.filter(
                            custom_plan__type='transactionfee_subscription').first()
                        if user_transactionfee_subscription:
                            sub_container = stripe.Subscription.retrieve(user_transactionfee_subscription.subscription_id)
                        else:
                            tr_fee_plan = CustomStripePlan.objects.get(type='transactionfee_subscription')

                            sub_container = stripe.Subscription.create(
                                customer=sale_transaction_fee.user.stripe_customer.customer_id,
                                plan=tr_fee_plan.stripe_id,
                                metadata={'custom_plan_id': tr_fee_plan.stripe_id, 'user_id': sale_transaction_fee.user.id, 'custom': True,
                                          'custom_plan_type': 'transactionfee_subscription'}
                            )
                            sub_id_to_use = sub_container.id
                            si = stripe.SubscriptionItem.retrieve(sub_container['items']['data'][0]["id"])

                            custom_stripe_subscription = CustomStripeSubscription()
                            custom_stripe_subscription.data = json.dumps(sub_container)
                            custom_stripe_subscription.status = sub_container['status']
                            custom_stripe_subscription.period_start = arrow.get(
                                sub_container['current_period_start']).datetime
                            custom_stripe_subscription.period_end = arrow.get(sub_container['current_period_end']).datetime
                            custom_stripe_subscription.user = sale_transaction_fee.user
                            custom_stripe_subscription.custom_plan = tr_fee_plan
                            custom_stripe_subscription.subscription_id = sub_id_to_use
                            custom_stripe_subscription.subscription_item_id = si.id

                            custom_stripe_subscription.save()

                        upcoming_invoice_item = add_invoice(sub_container, 'sale_fee',
                                                            sale_transaction_fee.fee_value, False, "Order Sales Fee")
                        if upcoming_invoice_item:
                            sale_transaction_fee.processed = True
                            sale_transaction_fee.save()
                    except:
                        skip_user_ids.append(sale_transaction_fee.user.id)
                        capture_exception()

                elif sale_transaction_fee.user.profile.from_shopify_app_store():
                    # shopify billing (using usage charge api)
                    charge_id = add_shopify_usage_invoice(sale_transaction_fee.user, 'sale_fee', sale_transaction_fee.fee_value,
                                                          "Order Sales Fee")

                    if charge_id:
                        sale_transaction_fee.processed = True
                        sale_transaction_fee.save()
            except:
                capture_exception()
