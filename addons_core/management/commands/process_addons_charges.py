from django.db.models import F

import arrow
import simplejson as json
from addons_core.models import AddonUsage

from lib.exceptions import capture_exception
from shopified_core.management import DropifiedBaseCommand
from stripe_subscription.models import CustomStripePlan, CustomStripeSubscription
from stripe_subscription.stripe_api import stripe
from stripe_subscription.utils import add_invoice


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

        addon_usages = AddonUsage.objects.exclude(billed_at__gte=F('cancelled_at'), cancelled_at__isnull=False)
        if options['user_id']:
            addon_usages = addon_usages.filter(user_id=options['user_id'])
        addon_usages = addon_usages.iterator()

        for addon_usage in addon_usages:

            try:
                if addon_usage.user.is_stripe_customer():
                    # getting Stripe subscription container

                    user_stripe_subscription = addon_usage.user.customstripesubscription_set.filter(
                        custom_plan__type='addons_subscription').first()

                    if user_stripe_subscription:
                        sub_container = stripe.Subscription.retrieve(user_stripe_subscription.subscription_id)
                    else:
                        AddonsPlan = CustomStripePlan.objects.get(type='addons_subscription')

                        sub_container = stripe.Subscription.create(
                            customer=addon_usage.user.stripe_customer.customer_id,
                            plan=AddonsPlan.stripe_id,
                            metadata={'custom_plan_id': AddonsPlan.stripe_id, 'user_id': addon_usage.user.id,
                                      'custom': True,
                                      'custom_plan_type': 'addons_subscription'}
                        )
                        sub_id_to_use = sub_container.id
                        si = stripe.SubscriptionItem.retrieve(sub_container['items']['data'][0]["id"])

                        custom_stripe_subscription = CustomStripeSubscription()
                        custom_stripe_subscription.data = json.dumps(sub_container)
                        custom_stripe_subscription.status = sub_container['status']
                        custom_stripe_subscription.period_start = arrow.get(
                            sub_container['current_period_start']).datetime
                        custom_stripe_subscription.period_end = arrow.get(sub_container['current_period_end']).datetime
                        custom_stripe_subscription.user = addon_usage.user
                        custom_stripe_subscription.custom_plan = AddonsPlan
                        custom_stripe_subscription.subscription_id = sub_id_to_use
                        custom_stripe_subscription.subscription_item_id = si.id

                        custom_stripe_subscription.save()

                    upcoming_invoice_item = add_invoice(sub_container, 'addons_usage',
                                                        addon_usage.usage_charge(), False, "Addons Usage Fee")

                    if upcoming_invoice_item:
                        today = arrow.get()
                        addon_usage.billed_at = today.format()
                        addon_usage.save()

                elif addon_usage.user.profile.from_shopify_app_store():
                    # TODO shopify billing can be here (using usage charge api)
                    pass
            except:
                capture_exception()
