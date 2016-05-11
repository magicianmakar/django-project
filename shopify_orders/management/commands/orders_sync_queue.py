from django.core.management.base import BaseCommand, CommandError
from leadgalaxy.models import ShopifyStore, GroupPlan, AppPermission
from leadgalaxy import utils

from raven.contrib.django.raven_compat.models import client as raven_client

from shopify_orders.models import ShopifySyncStatus


class Command(BaseCommand):
    help = 'Sync Shopify Orders For a stores with a permission or within a Plan'

    synced_store = []
    sync_type = 'orders'

    def add_arguments(self, parser):
        parser.add_argument('--plan', dest='plan_id', action='append', type=int, help='Plan ID')
        parser.add_argument('--store', dest='store_id', action='append', type=int, help='Store ID')
        parser.add_argument('--permission', dest='permission', action='append', type=str, help='Users with permission')

    def handle(self, *args, **options):
        try:
            self.start_command(*args, **options)
        except:
            raven_client.captureException()

    def start_command(self, *args, **options):
        if not options['plan_id']:
            options['plan_id'] = []

        if not options['store_id']:
            options['store_id'] = []

        if not options['permission']:
            options['permission'] = []

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
                        self.handle_store(profile.user.shopifystore_set.all())

                for bundle in p.featurebundle_set.all():
                    self.write_success('Sync Orders for Bundle: {}'.format(bundle.title))
                    for profile in bundle.userprofile_set.select_related('user').all():
                        self.handle_store(profile.user.shopifystore_set.all())

    def handle_store(self, store):
        if store.id in self.synced_store or not store.is_active:
            return

        webhooks = utils.attach_webhooks(store)
        self.write_success('    + {} webhooks for {}'.format(len(webhooks), store.title))

        try:
            ShopifySyncStatus.objects.get(store=store, sync_type=self.sync_type)
        except ShopifySyncStatus.DoesNotExist:
            self.write_success('Sync Store: {}'.format(store.title))

            sync = ShopifySyncStatus(store=store, sync_type=self.sync_type)
            sync.save()

        self.synced_store.append(store.id)

    def write_success(self, message):
        self.stdout.write(self.style.MIGRATE_SUCCESS(message))
