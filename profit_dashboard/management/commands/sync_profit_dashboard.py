import simplejson as json
from datetime import timedelta

from django.db import transaction
from django.utils import timezone
from django.db.models import CharField, Value
from django.db.models.functions import Concat
from tqdm import tqdm

from shopified_core.management import DropifiedBaseCommand
from leadgalaxy.models import ShopifyOrderTrack
from profit_dashboard.models import AliexpressFulfillmentCost


class Command(DropifiedBaseCommand):
    help = 'Sync Aliexpress fulfillment costs from last month'

    def add_arguments(self, parser):
        parser.add_argument('--noprogress', dest='progress',
                            action='store_false', help='Hide Progress')

    def start_command(self, *args, **options):
        progress = options['progress']

        order_source = Concat('order_id', Value('-'), 'source_id', output_field=CharField())
        start_date = timezone.now() - timedelta(days=32)
        end_date = timezone.now()

        tracks = ShopifyOrderTrack.objects.filter(
            store_id__isnull=False,
            source_id__isnull=False,
            created_at__range=(start_date, end_date),
            data__icontains='aliexpress'
        ).annotate(
            order_source=order_source
        ).exclude(
            order_source__in=AliexpressFulfillmentCost.objects.annotate(order_source=order_source).values('order_source')
        )

        count = tracks.count()
        if progress:
            obar = tqdm(total=count)

        start = 0
        steps = 5000

        while start < count:
            with transaction.atomic():
                aliexpress_fulfillment_costs = []
                order_sources = []

                for track in tracks[start:start + steps]:
                    data = json.loads(track.data) if track.data else {}
                    total_cost = 0.0
                    shipping_cost = 0.0
                    products_cost = 0.0

                    if data.get('aliexpress') and data.get('aliexpress').get('order_details') and \
                            data.get('aliexpress').get('order_details').get('cost'):
                        total_cost = data['aliexpress']['order_details']['cost'].get('total', 0)
                        shipping_cost = data['aliexpress']['order_details']['cost'].get('shipping', 0)
                        products_cost = data['aliexpress']['order_details']['cost'].get('products', 0)

                    if track.order_source not in order_sources and (total_cost > 0 or shipping_cost > 0 or products_cost > 0):
                        aliexpress_fulfillment_costs.append(AliexpressFulfillmentCost(
                            store_id=track.store_id,
                            order_id=track.order_id,
                            source_id=track.source_id,
                            created_at=track.created_at.date(),
                            shipping_cost=shipping_cost,
                            products_cost=products_cost,
                            total_cost=total_cost
                        ))
                        order_sources.append(track.order_source)

                    start += 1
                    if progress:
                        obar.update(1)

                AliexpressFulfillmentCost.objects.bulk_create(aliexpress_fulfillment_costs)

        if progress:
            obar.close()
