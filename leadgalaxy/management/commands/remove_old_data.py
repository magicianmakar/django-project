from pprint import pprint
from collections import defaultdict

from django.utils import timezone

from shopified_core.commands import DropifiedBaseCommand
from leadgalaxy.models import ShopifyOrderTrack
from shopify_orders.models import ShopifyOrder, ShopifyOrderLog
from profit_dashboard.models import AliexpressFulfillmentCost
from product_alerts.models import ProductChange


class Command(DropifiedBaseCommand):

    def add_arguments(self, parser):
        parser.add_argument('--max-count', type=int, default=2_000_000, help='Max number of deleted items')
        parser.add_argument('--delete-chunks', type=int, default=5000, help='Number of items to delete at once')
        parser.add_argument('--uptime', action='store', type=int, default=10, help='Maximum task uptime (minutes)')
        parser.add_argument('--before-years', action='store', type=int, default=3, help='Delete before this many years')
        parser.add_argument('--before-days', action='store', type=int, default=0, help='Delete before this many days')
        parser.add_argument('type', type=str, choices=['orders', 'tracks', 'logs', 'costs', 'alerts'], help='Type of data to remove')

    def start_command(self, *args, **options):
        # two years from now
        self.model_type = options['type']

        before_date = None
        if options['before_days'] and options['before_years']:
            self.write('You can only specify one of --before-days or --before-years')
        elif options['before_days']:
            before_date = timezone.now() - timezone.timedelta(days=options['before_days'])
        elif options['before_years']:
            before_date = timezone.now() - timezone.timedelta(days=options['before_years'] * 365)
        else:
            self.write('You must specify one of --before-days or --before-years')

        if not before_date:
            return

        limit = options['delete_chunks']
        max_count = options['max_count']

        print(f'> get {limit} {self.model_type} before_date {before_date:%Y-%m-%d}')

        deleted_map = defaultdict(int)
        deleted_total = 0

        start_time = timezone.now()
        while True:
            try:
                items = self.get_model().objects.filter(created_at__lt=before_date).only('id', 'created_at').order_by('created_at')
                first_item = items.first()
                if first_item:
                    print(f'{first_item.id} {first_item.created_at:%Y-%m-%d} => '.rjust(44), end='')
                    if first_item.created_at > before_date:
                        print('>> created_at > before_date - stop deleting')  # should never happen
                        break
                else:
                    print('>> no more items to delete')
                    break

                items_ids = items[:limit].values_list('id', flat=True)

                if len(items_ids) != limit:
                    print('> items len:', len(items_ids))

                if not items_ids:
                    break

                deleted, details = self.get_model().objects.filter(id__in=items_ids).delete()
                deleted_total += deleted
                for key, val in details.items():
                    deleted_map[key] += val

                print('Deleted:', ' | '.join(f'{key}: {val:3,}' for key, val in deleted_map.items()), '| Total:', f'{deleted_total:3,}')

                # check start_time
                if timezone.now() - start_time > timezone.timedelta(minutes=options['uptime']):
                    print('>>> uptime limit reached')
                    break

                max_count -= limit
                if max_count <= 0:
                    print('>>> max count reached')
                    break

            except KeyboardInterrupt:
                break

        pprint({
            'total': f'{deleted_total:3,}',
            **deleted_map
        })

        print('> Done')

    def get_model(self):
        if self.model_type == 'orders':
            return ShopifyOrder
        elif self.model_type == 'tracks':
            return ShopifyOrderTrack
        elif self.model_type == 'logs':
            return ShopifyOrderLog
        elif self.model_type == 'costs':
            return AliexpressFulfillmentCost
        elif self.model_type == 'alerts':
            return ProductChange
        else:
            print(f'Unknown model type: {self.model_type}')
