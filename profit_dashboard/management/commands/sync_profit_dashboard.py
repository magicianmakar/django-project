import arrow

from lib.exceptions import capture_exception

from shopified_core.management import DropifiedBaseCommand
from leadgalaxy.models import ShopifyOrderTrack
from profit_dashboard.models import AliexpressFulfillmentCost
from profit_dashboard.utils import get_costs_from_track


class Command(DropifiedBaseCommand):
    help = 'Sync Aliexpress fulfillment costs from last month'

    def add_arguments(self, parser):
        parser.add_argument('--noprogress', dest='progress', action='store_false',
                            help='Hide Progress')

        parser.add_argument('--store', dest='store', action='append', type=int,
                            help='Save fulfillment data for this stores only')

        parser.add_argument('--reset', dest='reset', action='store_true',
                            help='Delete All saved fulfillment cost data')

        parser.add_argument('--days', dest='days', action='store', type=int, default=30,
                            help='Save fulfillment data for orders made in the last number of days')

    def start_command(self, *args, **options):
        progress = options['progress']

        tracks = ShopifyOrderTrack.objects.filter(
            data__icontains='aliexpress'
        )

        if options.get('store'):
            tracks = tracks.filter(store__in=options['store'])

        if options.get('days') > 0:
            tracks = tracks.filter(created_at__gte=arrow.utcnow().replace(days=-options['days']).datetime)

        if options.get('reset') and options.get('store'):
            self.write('Reset Stores: {}'.format(options['store']))
            AliexpressFulfillmentCost.objects.filter(store__in=options['store']).delete()

        count = tracks.count()
        if progress:
            self.progress_total(count)

        start = 0
        steps = 5000
        first_track = None

        while start < count:
            aliexpress_fulfillment_costs = []
            source_ids = []

            for track in tracks[start:start + steps]:
                if first_track is None:
                    first_track = track

                try:
                    costs = get_costs_from_track(track)
                    if not costs or track.source_id in source_ids:
                        continue

                    aliexpress_fulfillment_costs.append(AliexpressFulfillmentCost(
                        store=track.store,
                        order_id=track.order_id,
                        source_id=track.source_id,
                        created_at=track.created_at.date(),
                        shipping_cost=costs['shipping_cost'],
                        products_cost=costs['products_cost'],
                        total_cost=costs['total_cost']
                    ))

                    source_ids.append(track.source_id)

                except:
                    capture_exception()

            self.progress_update()

            start += steps

            AliexpressFulfillmentCost.objects.bulk_create(aliexpress_fulfillment_costs)

            # Duplicated costs happen when first track is already imported
            is_duplicated = AliexpressFulfillmentCost.objects.filter(
                store=first_track.store,
                order_id=first_track.order_id,
                source_id=first_track.source_id
            ).count() > 1
            if is_duplicated:
                self.write('Duplicated cost found! Reset costs before sync is advise. (--reset)')

        self.progress_close()
