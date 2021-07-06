import arrow
from django.contrib.auth.models import User
from django.db.models import Q
from tqdm import tqdm

from lib.exceptions import capture_exception
from leadgalaxy.models import GroupPlan
from shopified_core.commands import DropifiedBaseCommand
from shopify_subscription.models import ShopifySubscription, ShopifySubscriptionWarning


class Command(DropifiedBaseCommand):
    help = 'Ask shopify users to subscribe again unexpected cancellations'

    def add_arguments(self, parser):
        parser.add_argument(
            '--users', dest='user_ids', action='append', type=int,
            help='Check single or multiple users')

        parser.add_argument(
            '--days_ago', dest='days_ago', action='store', type=int,
            help='Check subscriptions updated as far as that many days')

        parser.add_argument('--progress', dest='progress', action='store_true', help='Show sync progress')

    def start_command(self, *args, **options):
        self.progress = options.get('progress')
        days_ago = options.get('days_ago') or 7

        # Update shopify subscriptions
        outdated_subscriptions = ShopifySubscription.objects.exclude(
            user__profile__plan__slug='shopify-free-plan'
        ).filter(
            user__profile__plan__payment_gateway='shopify',
            status__in=['pending', 'active', 'expired'],
            updated_at__range=(
                arrow.get().shift(days=days_ago * -1).datetime,
                arrow.get().shift(days=-2).datetime
            )
        )
        if self.progress:
            progress_bar = tqdm(total=len(outdated_subscriptions))

        for subscription in outdated_subscriptions:
            if self.progress:
                progress_bar.update(1)
            try:
                subscription.refresh()
            except:
                capture_exception()

        if self.progress:
            progress_bar.close()

        users = User.objects.select_related('shopify_subscription_warning').exclude(
            profile__plan__slug='shopify-free-plan',
            profile__plan__payment_interval='yearly'
        ).filter(
            ~Q(shopifysubscription__status__in=['pending', 'active']),
            profile__plan__payment_gateway='shopify',
            shopifysubscription__status__in=['expired', 'cancelled']
        ).distinct()

        user_ids = options.get('user_ids')
        if user_ids:
            users = users.filter(id__in=user_ids)

        if self.progress:
            progress_bar = tqdm(total=users.count())

        for user in users:
            shopify_subscription = user.shopifysubscription_set.filter(charge_type='recurring').last()
            if shopify_subscription.status not in ['expired', 'cancelled']:
                continue

            try:
                if user.shopify_subscription_warning.is_expired:
                    # Uninstalling webhooks might complicate if they re-activate the subscription
                    user.profile.change_plan(GroupPlan.objects.get(
                        payment_gateway='shopify',
                        slug='shopify-free-plan'))

            except ShopifySubscriptionWarning.DoesNotExist:
                pass

            warning, created = ShopifySubscriptionWarning.objects.get_or_create(
                user=user,
                defaults={
                    'shopify_subscription': shopify_subscription,
                    'expired_at': arrow.get().shift(days=30).date()
                }
            )

            warning.create_charge()
            warning.send_email()
            warning.save()

            if self.progress:
                progress_bar.update(1)

        if self.progress:
            progress_bar.close()
