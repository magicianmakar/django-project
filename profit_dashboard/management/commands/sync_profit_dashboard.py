import arrow

from lib.exceptions import capture_exception
from django.contrib.contenttypes.models import ContentType

from shopified_core.management import DropifiedBaseCommand
from shopified_core.utils import get_store_model, get_track_model
from profit_dashboard.models import AliexpressFulfillmentCost
from profit_dashboard.utils import get_costs_from_track
from profits.utils import get_costs_from_track as generic_get_costs_from_track
from profits.models import FulfillmentCost


class Command(DropifiedBaseCommand):
    help = 'Sync Aliexpress fulfillment costs from last month'

    def add_arguments(self, parser):
        parser.add_argument('--noprogress', dest='progress', action='store_false',
                            help='Hide Progress')

        parser.add_argument('--store', action='append', type=int,
                            help='Save fulfillment data for this stores only')

        parser.add_argument('--reset', action='store_true',
                            help='Delete All saved fulfillment cost data')

        parser.add_argument('--days', action='store', type=int, default=365,
                            help='Save fulfillment data for orders made in the last number of days')

        parser.add_argument('--store-type', default='shopify',
                            help='Platform to be used [shopify, chq, woo, gkart, bigcommerce]')

    def get_fulfillment_cost_model(self):
        if self.store_type in ['chq', 'woo', 'gkart', 'bigcommerce']:
            return FulfillmentCost

        return AliexpressFulfillmentCost

    @property
    def store_content_type(self):
        if not hasattr(self, '_store_content_type'):
            self._store_content_type = ContentType.objects.get_for_model(
                get_store_model(self.store_type)
            )
        return self._store_content_type

    def filter_fulfillment_costs(self, store_id=None):
        stores = [store_id] if store_id else self.store_ids

        if self.store_type in ['chq', 'woo', 'gkart', 'bigcommerce']:
            return FulfillmentCost.objects.filter(
                store_content_type=self.store_content_type,
                store_object_id__in=stores,
            )

        return AliexpressFulfillmentCost.objects.filter(store__in=stores)

    def get_fulfillment_cost_instance(self, store, **kwargs):
        fulfillment_cost = self.get_fulfillment_cost_model()(**kwargs)
        if self.store_type in ['chq', 'woo', 'gkart', 'bigcommerce']:
            fulfillment_cost.store = store
            fulfillment_cost.store_content_type = self.store_content_type
            fulfillment_cost.store_object_id = store.id
        else:
            fulfillment_cost.store = store

        return fulfillment_cost

    def get_costs(self, track):
        if self.store_type in ['chq', 'woo', 'gkart', 'bigcommerce']:
            return generic_get_costs_from_track(track)

        return get_costs_from_track(track)

    def start_command(self, *args, **options):
        progress = options['progress']
        self.store_type = options['store_type']
        self.store_ids = options.get('store')

        order_track_model = get_track_model(self.store_type)
        fulfillment_cost_model = self.get_fulfillment_cost_model()

        tracks = order_track_model.objects.filter(
            data__icontains='aliexpress'
        )

        if self.store_ids:
            tracks = tracks.filter(store__in=self.store_ids)

        if options.get('days') > 0:
            tracks = tracks.filter(created_at__gte=arrow.utcnow().replace(days=-options['days']).datetime)

        if options.get('reset') and self.store_ids:
            self.write('Reset Stores: {}'.format(self.store_ids))
            self.filter_fulfillment_costs().delete()

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
                    costs = self.get_costs(track)
                    if not costs or track.source_id in source_ids:
                        continue

                    aliexpress_fulfillment_costs.append(self.get_fulfillment_cost_instance(
                        track.store,
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

            self.progress_update(steps)

            start += steps

            fulfillment_cost_model.objects.bulk_create(aliexpress_fulfillment_costs)

            # Duplicated costs happen when first track is already imported
            is_duplicated = self.filter_fulfillment_costs(first_track.store.id).filter(
                order_id=first_track.order_id,
                source_id=first_track.source_id
            ).count() > 1
            if is_duplicated:
                self.write('Duplicated cost found! Reset costs before sync is advise. (--reset)')

        self.progress_close()
