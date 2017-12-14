import arrow

from tqdm import tqdm
from raven.contrib.django.raven_compat.models import client as raven_client

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
            tracks = tracks.filter(created_at__gte=arrow.utcnow().replace(days=-options['store']).datetime)

        if options.get('reset') and options.get('store'):
            self.write('Reset Stores: {}'.format(options['store']))
            AliexpressFulfillmentCost.objects.filter(store__in=options['store']).delete()

        count = tracks.count()
        if progress:
            obar = tqdm(total=count)

        start = 0
        steps = 5000

        while start < count:
            aliexpress_fulfillment_costs = []
            source_ids = []

            for track in tracks[start:start + steps]:
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
                    raven_client.captureException()

            if progress:
                obar.update(steps)

            start += steps

            AliexpressFulfillmentCost.objects.bulk_create(aliexpress_fulfillment_costs)

        if progress:
            obar.close()
