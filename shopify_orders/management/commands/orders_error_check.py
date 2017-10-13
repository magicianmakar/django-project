from django.utils import timezone

from tqdm import tqdm

from datetime import timedelta

from shopified_core.management import DropifiedBaseCommand
from leadgalaxy.models import ShopifyOrderTrack
from shopify_orders.utils import OrderErrorsCheck


class EmptyProgress:
    def update(self, n):
        pass

    def close(self):
        pass


class Command(DropifiedBaseCommand):
    help = 'Check for errors in Shopify Order Tracks'

    orders_check = None

    def add_arguments(self, parser):
        parser.add_argument('--store', dest='store_id', action='append', type=int, help='Store ID')
        parser.add_argument('--since', dest='since', action='store', type=int, help='Check Order Created Since Days')
        parser.add_argument('--all-orders', dest='all', action='store_true', help='Check All Orders not only pending one')
        parser.add_argument('--commit', dest='commit', action='store_true', help='Do not save found errors to the database')
        parser.add_argument('--progress', dest='progress', action='store_true', help='Show Check Progress')

    def start_command(self, *args, **options):
        tracks = ShopifyOrderTrack.objects.filter(data__contains='contact_name')

        if not options['all']:
            tracks = tracks.filter(errors=None)

        if options['store_id']:
            tracks = tracks.filter(store__in=options['store_id'])

        if options['since']:
            tracks = tracks.filter(created_at__gte=timezone.now() - timedelta(days=options['since']))

        tracks = tracks.order_by('-created_at')

        total_count = tracks.count()

        self.write_success('Checking {} Tracks'.format(total_count))

        if options['progress']:
            obar = tqdm(total=total_count)
        else:
            obar = EmptyProgress()

        steps = 1000
        start = 0

        self.orders_check = OrderErrorsCheck(self.stdout if options['progress'] else None)

        while start <= total_count:
            for track in tracks[start:start + steps]:
                self.orders_check.check(track, options['commit'])

            obar.update(steps)
            start += steps

        obar.close()

        self.write_success('Errors: {} - Ignored: {}'.format(
            self.orders_check.errors, self.orders_check.ignored))
