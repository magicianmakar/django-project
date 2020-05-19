from django.contrib.auth.models import User

import arrow
import simplejson as json
from lib.exceptions import capture_exception

from shopified_core.management import DropifiedBaseCommand
from stripe_subscription.models import CustomStripePlan, CustomStripeSubscription
from stripe_subscription.stripe_api import stripe


class Command(DropifiedBaseCommand):
    help = 'Apply CallFlex Plan manually'

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
            default=False,
            help='Custom Subscription CallFLex Plan to apply'
        )

        parser.add_argument(
            '-perm',
            '--permission',
            default='phone_automation.use',
            help='Permission to filter'
        )

    def start_command(self, *args, **options):
        users = User.objects.filter(profile__plan__permissions__name=options['permission'])

        if options['user_id']:
            users = User.objects.filter(pk=options['user_id'])

        for user in users.iterator():
            try:
                self.write(f"Processing User ID:{user.pk} ")
                plan = CustomStripePlan.objects.get(id=options['plan_id'])

                subscription = user.stripesubscription_set.latest('created_at')
                sub = subscription.refresh()
                sub_id_to_use = sub.id

                user_callflex_subscription = user.customstripesubscription_set.filter(
                    custom_plan__type='callflex_subscription').first()
                if user_callflex_subscription:
                    sub_container = stripe.Subscription.retrieve(user_callflex_subscription.subscription_id)
                else:
                    sub_container = sub

                if plan.interval != sub_container['items']['data'][0]["plan"]["interval"]:
                    # check if main subscription match with interval and can be combined to
                    if plan.interval != sub['items']['data'][0]["plan"]["interval"]:
                        need_new_sub_flag = True
                    else:
                        # main sub can be used, take it instead
                        sub_container = sub
                        need_new_sub_flag = False
                    # delete current subscription, as new one will be created with another interval
                    if user_callflex_subscription:
                        user_callflex_subscription.safe_delete()
                else:
                    need_new_sub_flag = False

                # checking existing subscription
                user_callflex_subscription = user.customstripesubscription_set.filter(
                    custom_plan__type='callflex_subscription').first()

                if user_callflex_subscription:
                    stripe.SubscriptionItem.modify(
                        user_callflex_subscription.subscription_item_id,

                        plan=plan.stripe_id,
                        metadata={'plan_id': plan.id, 'user_id': user.id}
                    )
                    si = stripe.SubscriptionItem.retrieve(user_callflex_subscription.subscription_item_id)
                    custom_stripe_subscription = user_callflex_subscription
                else:
                    if need_new_sub_flag:
                        # creating new subscription for callflex plan
                        sub_container = stripe.Subscription.create(
                            customer=user.stripe_customer.customer_id,
                            plan=plan.stripe_id,
                            metadata={'custom_plan_id': plan.id, 'user_id': user.id, 'custom': True,
                                      'custom_plan_type': 'callflex_subscription'}
                        )
                        sub_id_to_use = sub_container.id
                        si = stripe.SubscriptionItem.retrieve(sub_container['items']['data'][0]["id"])
                    else:
                        si = stripe.SubscriptionItem.create(
                            subscription=sub_id_to_use,
                            plan=plan.stripe_id,
                            metadata={'plan_id': plan.id, 'user_id': user.id}
                        )

                    custom_stripe_subscription = CustomStripeSubscription()

                custom_stripe_subscription.data = json.dumps(sub_container)
                custom_stripe_subscription.status = sub_container['status']
                custom_stripe_subscription.period_start = arrow.get(sub_container['current_period_start']).datetime
                custom_stripe_subscription.period_end = arrow.get(sub_container['current_period_end']).datetime
                custom_stripe_subscription.user = user
                custom_stripe_subscription.custom_plan = plan
                custom_stripe_subscription.subscription_id = sub_id_to_use
                custom_stripe_subscription.subscription_item_id = si.id

                custom_stripe_subscription.save()

            except:
                capture_exception()
