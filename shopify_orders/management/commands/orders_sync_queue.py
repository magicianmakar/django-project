from django.core.management.base import CommandError

from shopified_core.management import DropifiedBaseCommand
from shopify_orders.models import ShopifySyncStatus
from leadgalaxy.models import ShopifyStore, GroupPlan, AppPermission, UserProfile
from leadgalaxy import utils

from lib.exceptions import capture_exception


class Command(DropifiedBaseCommand):
    help = 'Sync Shopify Orders For a stores with a permission or within a Plan'

    synced_store = []
    queued_store = []
    sync_type = 'orders'

    def add_arguments(self, parser):
        parser.add_argument('--plan', dest='plan_id', action='append', type=int, help='Plan ID')
        parser.add_argument('--user', dest='user_id', action='append', type=int, help='User ID')
        parser.add_argument('--store', dest='store_id', action='append', type=int, help='Store ID')
        parser.add_argument('--permission', dest='permission', action='append', type=str, help='Users with permission')
        parser.add_argument('--count', dest='count', action='store_true', help='Update Orders count')

    def start_command(self, *args, **options):
        for i in ['plan_id', 'user_id', 'store_id', 'permission']:
            if not options[i]:
                options[i] = []

        if options.get('count'):
            total_orders = 0
            for sync in ShopifySyncStatus.objects.all():
                store = sync.store

                self.write_success('Orders count for: {}'.format(store.title))

                try:
                    sync.orders_count = store.get_orders_count(all_orders=True)
                    total_orders += sync.orders_count
                except:
                    sync.orders_count = -1

                sync.save()

            self.write_success('Total Orders: {}'.format(total_orders))

            return

        for plan_id in options['plan_id']:
            try:
                plan = GroupPlan.objects.get(pk=plan_id)
            except GroupPlan.DoesNotExist:
                raise CommandError('Plan "%s" does not exist' % plan_id)

            self.write_success('Sync Orders for plan: {}'.format(plan.title))

            stores = ShopifyStore.objects.filter(user__profile__plan=plan)
            self.stdout.write(self.style.HTTP_INFO('Stores count: %d' % stores.count()))
            for store in stores:
                self.handle_store(store)

        for user_id in options['user_id']:
            for store in UserProfile.objects.get(user_id=user_id).get_shopify_stores():
                self.handle_store(store)

        for store_id in options['store_id']:
            try:
                store = ShopifyStore.objects.get(pk=store_id)
            except ShopifyStore.DoesNotExist:
                raise CommandError('Store "%s" does not exist' % store_id)

            self.write_success('Sync Orders for store: {}'.format(store.title))

            self.handle_store(store)

        for permission in options['permission']:
            for p in AppPermission.objects.filter(name=permission):
                for plan in p.groupplan_set.all():
                    self.write_success('Sync Orders for Plan: {}'.format(plan.title))

                    for profile in plan.userprofile_set.select_related('user').all():
                        for store in profile.get_shopify_stores():
                            self.handle_store(store)

                for bundle in p.featurebundle_set.all():
                    self.write_success('Sync Orders for Bundle: {}'.format(bundle.title))
                    for profile in bundle.userprofile_set.select_related('user').all():
                        for store in profile.get_shopify_stores():
                            self.handle_store(store)

        self.write_success('Total Queued Store: {}/{}'.format(len(self.queued_store), len(self.synced_store)))

    def handle_store(self, store):
        if store.id in self.synced_store or not store.is_active:
            return

        try:
            ShopifySyncStatus.objects.get(store=store, sync_type=self.sync_type)
        except ShopifySyncStatus.DoesNotExist:
            self.write_success('Sync Store: {}'.format(store.title))
            sync = ShopifySyncStatus(store=store, sync_type=self.sync_type)

            try:
                sync.orders_count = store.get_orders_count(all_orders=True)

                webhooks = utils.attach_webhooks(store)
                self.write_success('    + Install {} webhooks'.format(len(webhooks)))

                self.queued_store.append(store.id)
            except:
                sync.sync_status = 4
                capture_exception()

            sync.save()

        self.synced_store.append(store.id)
