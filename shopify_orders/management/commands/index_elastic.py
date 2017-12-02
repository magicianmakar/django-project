from tqdm import tqdm

from shopified_core.management import DropifiedBaseCommand
from shopify_orders.models import ShopifySyncStatus, ShopifyOrder
from shopify_orders.utils import is_store_synced, get_elastic
from leadgalaxy.models import ShopifyStore

from elasticsearch.exceptions import NotFoundError
from elasticsearch.helpers import streaming_bulk


class Command(DropifiedBaseCommand):

    def add_arguments(self, parser):
        parser.add_argument('--store', dest='store', action='append', type=int, help='Store Orders to index')
        parser.add_argument('--user', dest='user', action='append', type=int, help='User Stores to index')

    def start_command(self, *args, **options):
        stores = ShopifyStore.objects.filter(is_active=True, shopifysyncstatus__sync_status__in=[2, 5])

        if options.get('store'):
            stores = stores.filter(id__in=options['store'])

        if options.get('user'):
            stores = stores.filter(user__in=options['user'])

        self.es = get_elastic()

        self.set_mappings()

        stores_bar = tqdm(total=stores.count())

        for store in stores:
            stores_bar.update(1)
            if not is_store_synced(store):
                continue

            orders = ShopifyOrder.objects.prefetch_related('shopifyorderline_set').filter(store_id=store.id)
            orders_count = orders.count()

            orders_bar = tqdm(desc=store.title, total=orders_count)
            for ok, item in streaming_bulk(self.es, self.get_orders_iterator(orders, orders_count)):
                orders_bar.update(1)

            ShopifySyncStatus.objects.filter(store=store).update(elastic=True)

            orders_bar.close()

        stores_bar.close()

    def get_orders_iterator(self, orders, count):
        start = 0
        steps = 5000

        while start < count:
            for order in orders[start:start + steps]:
                yield self.get_dataset(order)

                start += 1

    def set_mappings(self):
        try:
            self.es.indices.get(index='shopify-order')
        except NotFoundError:
            print 'Created Index...'
            self.es.indices.create(index='shopify-order', body={
                "mappings": {
                    "order": {
                        "properties": {
                            "city": {"type": "text"},
                            "customer_email": {"type": "keyword"},
                            "total_price": {"type": "float"},
                            "need_fulfillment": {"type": "long"},
                            "order_id": {"type": "long"},
                            "created_at": {"type": "date"},
                            "connected_items": {"type": "long"},
                            "updated_at": {"type": "date"},
                            "financial_status": {"type": "keyword"},
                            "fulfillment_status": {"type": "keyword"},
                            "items_count": {"type": "long"},
                            "user": {"type": "long"},
                            "country_code": {"type": "keyword"},
                            "cancelled_at": {"type": "date"},
                            "closed_at": {"type": "date"},
                            "tags": {"type": "text"},
                            "customer_id": {"type": "long"},
                            "order_number": {"type": "long"},
                            "zip_code": {"type": "keyword"},
                            "store": {"type": "long"},
                            "customer_name": {"type": "keyword"},
                            "product_ids": {"type": "long"},
                        }
                    }
                }
            })

    def get_dataset(self, order):
        return {
            "_index": "shopify-order",
            "_type": "order",
            "_id": order.id,
            "_source": {
                "store": order.store_id,
                "user": order.user_id,
                "order_id": order.order_id,
                "order_number": order.order_number,
                "customer_id": order.customer_id,
                "customer_name": order.customer_name,
                "customer_email": order.customer_email,
                "financial_status": order.financial_status,
                "fulfillment_status": order.fulfillment_status,
                "total_price": order.total_price,
                "tags": order.tags,
                "city": order.city,
                "zip_code": order.zip_code,
                "country_code": order.country_code,
                "items_count": order.items_count,
                "need_fulfillment": order.need_fulfillment,
                "connected_items": order.connected_items,
                "created_at": order.created_at,
                "updated_at": order.updated_at,
                "closed_at": order.closed_at,
                "cancelled_at": order.cancelled_at,
                "product_ids": [l.product_id for l in order.shopifyorderline_set.all()]
            }
        }
