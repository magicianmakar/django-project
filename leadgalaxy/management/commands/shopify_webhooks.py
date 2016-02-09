from django.core.management.base import BaseCommand, CommandError
from leadgalaxy.models import *
from leadgalaxy import utils


class Command(BaseCommand):
    help = 'Attach Shopify Webhooks to a specific Plan'

    def add_arguments(self, parser):
        parser.add_argument('action', nargs=1, type=str,
                            choices=['attach', 'detach'], help='Action')

        parser.add_argument('plan_id', nargs='+', type=int, help='Plan IDs')

    def handle(self, *args, **options):
        action = options['action'][0]
        for plan_id in options['plan_id']:
            try:
                plan = GroupPlan.objects.get(pk=plan_id)
            except GroupPlan.DoesNotExist:
                raise CommandError('Plan "%s" does not exist' % plan_id)

            self.stdout.write(self.style.MIGRATE_SUCCESS(
                '{} webhooks for plan: {}'.format(action.title(), plan.title)))

            stores = ShopifyStore.objects.filter(user__profile__plan=plan)
            self.stdout.write(self.style.HTTP_INFO('Stores count: %d' % stores.count()))
            for store in stores:
                if action == 'attach':
                    webhooks = utils.attach_webhooks(store)
                else:
                    webhooks = utils.detach_webhooks(store, True)

                if action != 'attach':
                    self.stdout.write(self.style.MIGRATE_SUCCESS('    * {}'.format(store.title)))
                elif len(webhooks) == 2:
                    self.stdout.write(self.style.MIGRATE_SUCCESS('    * {}: {}'.format(store.title, len(webhooks))))
                else:
                    self.stdout.write(self.style.ERROR('    * {}: {}'.format(store.title, len(webhooks))))
