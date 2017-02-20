from django.core.management.base import BaseCommand, CommandError
from leadgalaxy.models import *
from leadgalaxy import utils


class Command(BaseCommand):
    help = 'Attach Shopify Webhooks to a specific Plan'

    def add_arguments(self, parser):
        parser.add_argument('action', nargs=1, type=str,
                            choices=['attach', 'detach'], help='Action')

        parser.add_argument('--plan', dest='plan_id', action='append', type=int, help='Plan ID')
        parser.add_argument('--store', dest='store_id', action='append', type=int, help='Store ID')
        parser.add_argument('--permission', dest='permission', action='append', type=str, help='Users with permission')
        parser.add_argument('--delete_on_detach', dest='delete_on_detach',
                            action='store_true', help='Delete Saved Webhook on detach')

    def handle(self, *args, **options):
        action = options['action'][0]

        for i in ['plan_id', 'store_id', 'permission']:
            if not options[i]:
                options[i] = []

        for plan_id in options['plan_id']:
            try:
                plan = GroupPlan.objects.get(pk=plan_id)
            except GroupPlan.DoesNotExist:
                raise CommandError('Plan "%s" does not exist' % plan_id)

            self.write_success(u'{} webhooks for plan: {}'.format(action.title(), plan.title))

            stores = ShopifyStore.objects.filter(user__profile__plan=plan)
            self.stdout.write(self.style.HTTP_INFO('Stores count: %d' % stores.count()))
            for store in stores:
                self.handle_store(store, action, options['delete_on_detach'])

        for permission in options['permission']:
            for p in AppPermission.objects.filter(name=permission):
                for plan in p.groupplan_set.all():
                    self.write_success(u'{} webhooks for Plan: {}'.format(action.title(), plan.title))

                    for profile in plan.userprofile_set.select_related('user').all():
                        for store in profile.get_shopify_stores():
                            self.handle_store(store, action, options['delete_on_detach'])

                for bundle in p.featurebundle_set.all():
                    self.write_success(u'{} webhooks for Bundle: {}'.format(action.title(), bundle.title))
                    for profile in bundle.userprofile_set.select_related('user').all():
                        for store in profile.get_shopify_stores():
                            self.handle_store(store, action, options['delete_on_detach'])

        for store_id in options['store_id']:
            try:
                store = ShopifyStore.objects.get(pk=store_id)
            except ShopifyStore.DoesNotExist:
                raise CommandError('Store "%s" does not exist' % store_id)

            self.write_success(u'{} webhooks for store: {}'.format(action.title(), store.title))

            self.handle_store(store, action, options['delete_on_detach'])

    def handle_store(self, store, action, delete_on_detach):
        if action == 'attach':
            webhooks = utils.attach_webhooks(store)
            self.write_success(u'    + {}: {}'.format(store.title, len(webhooks)))
        else:
            webhooks = utils.detach_webhooks(store, delete_on_detach)
            self.write_success(u'    - {}'.format(store.title))

    def write_success(self, message):
        self.stdout.write(self.style.MIGRATE_SUCCESS(message))
