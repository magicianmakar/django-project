from raven.contrib.django.raven_compat.models import client as raven_client

import time
import math
import requests

from shopified_core.management import DropifiedBaseCommand
from shopify_orders.models import ShopifySyncStatus, ShopifyOrder, ShopifyOrderLine, ShopifyOrderShippingLine
from shopify_orders.utils import update_shopify_order, get_customer_name, get_datetime, safeInt, str_max, delete_store_orders
from leadgalaxy.models import ShopifyStore
from leadgalaxy.utils import get_shopify_order


class Command(DropifiedBaseCommand):
    help = 'Fetch Orders from Shopify API and store them in the database'

    sync_type = 'orders'
    total_order_fetch = 0  # Number of imported orders since command start

    def add_arguments(self, parser):
        parser.add_argument('--status', dest='sync_status', action='append',
                            type=int, help='Sync Store with the given status')

        parser.add_argument('--reset', dest='reset',
                            action='store_true', help='Delete All Imported Orders and queue stores for re-import')

        parser.add_argument('--progress', dest='progress',
                            action='store_true', help='Shopw Reset Progress')

        parser.add_argument('--store', dest='store_id', action='append', type=int, help='Store ID')
        parser.add_argument('--max_orders', dest='max_orders', type=int, help='Sync Stores with Maximum Orders count')
        parser.add_argument('--max_import', dest='max_import', type=int, help='Maximum number of orders to import')

    def reset_stores(self, store_ids, progress=False):
        for store in store_ids:
            store = ShopifyStore.objects.get(id=store)

            self.write_success(u'Reset Store: {}'.format(store.title))

            deleted = delete_store_orders(store)

            self.write_success('Deleted Orders: {}'.format(deleted))

            ShopifySyncStatus.objects.filter(store_id=store.id).update(sync_status=0, pending_orders=None, elastic=False)
            self.write_success('Done')

    def start_command(self, *args, **options):
        if options['reset']:
            if options['store_id']:
                self.reset_stores(options['store_id'], options['progress'])
            return

        if not options['sync_status']:
            options['sync_status'] = [0, 6]

        while True:
            try:
                order_sync = ShopifySyncStatus.objects.filter(sync_type=self.sync_type, sync_status__in=options['sync_status'])
                if options.get('max_orders'):
                    order_sync = order_sync.filter(orders_count__lte=options.get('max_orders'))

                if options['store_id']:
                    order_sync = order_sync.filter(store__in=options['store_id'])

                order_sync = order_sync.earliest('updated_at')

                if not order_sync:
                    break

            except ShopifySyncStatus.DoesNotExist:
                break

            if order_sync.sync_status == 6:
                self.reset_stores([order_sync.store.pk])

            order_sync.sync_status = 1
            order_sync.save()

            try:
                self.fetch_orders(order_sync.store)

                order_sync.sync_status = 2
                order_sync.elastic = False  # Orders are not indexed by default
                order_sync.revision = 2  # New imported (or re-imported) orders support Product filters by default
                order_sync.save()

                self.update_pending_orders(order_sync)

            except:
                raven_client.captureException(extra={'store': order_sync.store, 'user': order_sync.store.user})

                ShopifyOrder.objects.filter(store=order_sync.store).delete()

                order_sync.sync_status = 4
                order_sync.save()

            if options.get('max_import') and self.total_order_fetch > options.get('max_import'):
                break

    def fetch_orders(self, store):
        limit = 240
        count = store.get_orders_count(status='any', fulfillment='any', financial='any')

        shipping_method_filter = False

        self.write_success(u'Import {} Order for: {}'.format(count, store.title))
        if not count:
            return

        self.products_map = store.shopifyproduct_set.exclude(shopify_id=0) \
                                 .values_list('id', 'shopify_id') \
                                 .order_by('created_at')
        self.products_map = dict(map(lambda a: (a[1], a[0]), self.products_map))

        self.filtered_map = store.shopifyproduct_set.filter(is_excluded=True).values_list('shopify_id', flat=True)

        self.tracking_map = store.shopifyordertrack_set.values_list('id', 'line_id')
        self.tracking_map = dict(map(lambda a: (a[1], a[0]), self.tracking_map))

        self.imported_orders = []
        self.saved_orders = {}
        self.saved_orders_last = 0
        self.rate_limit = ''
        self.req_time = 0

        import_start = time.time()

        pages = int(math.ceil(count / float(limit)))
        for page in xrange(1, pages + 1):
            if count > 1000:
                imported_count = len(self.imported_orders)
                self.stdout.write('Page {} ({:0.2f}%) (Rate: {} - {:0.2f}s) (Imported: {})'.format(
                    page,
                    imported_count / float(count) * 100.0,
                    self.rate_limit,
                    self.req_time,
                    imported_count
                ))

            req_start = time.time()
            rep = requests.get(
                url=store.get_link('/admin/orders.json', api=True),
                params={
                    'page': page,
                    'limit': limit,
                    'status': 'any',
                    'fulfillment': 'any',
                    'financial': 'any'
                }
            )

            self.rate_limit = rep.headers.get('X-Shopify-Shop-Api-Call-Limit')
            self.req_time = time.time() - req_start

            rep = rep.json()
            self.total_order_fetch += len(rep['orders'])

            # Bulk import orders
            orders = []
            already_imported = []
            for order in rep['orders']:
                if order['id'] not in self.imported_orders:
                    orders.append(self.prepare_order(order, store))

                    self.imported_orders.append(order['id'])
                else:
                    already_imported.append(order['id'])
                    self.stdout.write('Order #{} Already Imported'.format(order['id']), self.style.WARNING)

            if len(orders):
                ShopifyOrder.objects.bulk_create(orders)
            else:
                self.stdout.write('Empty Orders', self.style.WARNING)

            self.load_saved_orders(store)

            # Bulk import order lines
            lines = []
            shipping_lines = []

            for order in rep['orders']:
                if order['id'] not in already_imported:
                    saved_order = self.get_saved_order(store, order['id'])

                    for line in self.prepare_lines(order, saved_order):
                        lines.append(line)

                    if shipping_method_filter:
                        for shipping_line in self.prepare_shipping_lines(order, saved_order):
                            shipping_lines.append(shipping_line)
                else:
                    self.stdout.write('Line Already Imported of order #{}'.format(order['id']), self.style.WARNING)

            if len(lines):
                ShopifyOrderLine.objects.bulk_create(lines)
            else:
                self.stdout.write('Empty Order Lines', self.style.WARNING)

            if len(shipping_lines):
                ShopifyOrderShippingLine.objects.bulk_create(shipping_lines)

        self.write_success('Orders imported in %d:%d' % divmod(time.time() - import_start, 60))

    def update_pending_orders(self, order_sync):
        store = order_sync.store

        while True:
            order_sync.refresh_from_db()
            order_id = order_sync.pop_pending_orders()

            if not order_id:
                break

            self.stdout.write('Update pending order #{}'.format(order_id))
            time.sleep(1)

            try:
                order = get_shopify_order(store, order_id)
                update_shopify_order(store, order, sync_check=False)
            except:
                raven_client.captureException()

    def load_saved_orders(self, store):
        self.saved_orders = {}
        for order in ShopifyOrder.objects.filter(store=store, user=store.user).filter(id__gte=self.saved_orders_last):
            if order.order_id not in self.saved_orders:
                self.saved_orders[order.order_id] = order
                self.saved_orders_last = max(self.saved_orders_last, order.id)

    def get_saved_order(self, store, order_id):
        saved_order = self.saved_orders.get(order_id)
        if saved_order is None:
            self.stdout.write('Get Order from database #{}'.format(order_id))
            saved_order = ShopifyOrder.objects.get(store=store, order_id=order_id)

        return saved_order

    def prepare_order(self, data, store):
        address = data.get('shipping_address', data.get('customer', {}).get('default_address', {}))
        customer = data.get('customer', address)

        connected_items = 0
        need_fulfillment = len(data.get('line_items', []))

        for line in data.get('line_items', []):
            product_id = self.products_map.get(safeInt(line['product_id']))
            track_id = self.tracking_map.get(safeInt(line['id']))

            if product_id:
                connected_items += 1

            if track_id or line['fulfillment_status'] == 'fulfilled' or line['product_id'] in self.filtered_map:
                need_fulfillment -= 1

        order = ShopifyOrder(
            store=store,
            user=store.user,
            order_id=data['id'],
            order_number=data['number'],
            customer_id=customer.get('id', 0),
            customer_name=str_max(get_customer_name(customer), 255),
            customer_email=str_max(customer.get('email'), 255),
            financial_status=data['financial_status'],
            fulfillment_status=data['fulfillment_status'],
            total_price=data['total_price'],
            tags=data['tags'],
            city=str_max(address.get('city'), 63),
            zip_code=str_max(address.get('zip'), 31),
            country_code=str_max(address.get('country_code'), 31),
            items_count=len(data.get('line_items', [])),
            need_fulfillment=need_fulfillment,
            connected_items=connected_items,
            created_at=get_datetime(data['created_at']),
            updated_at=get_datetime(data['updated_at']),
            closed_at=get_datetime(data['closed_at']),
            cancelled_at=get_datetime(data['cancelled_at']),
        )

        return order

    def prepare_lines(self, data, order):
        lines = []
        for line in data.get('line_items', []):
            lines.append(ShopifyOrderLine(
                order=order,
                line_id=line['id'],
                shopify_product=safeInt(line['product_id']),
                title=line['title'],
                price=line['price'],
                quantity=line['quantity'],
                variant_id=safeInt(line.get('variant_id')),
                variant_title=line['variant_title'],
                fulfillment_status=line['fulfillment_status'],
                product_id=self.products_map.get(safeInt(line['product_id'])),
                track_id=self.tracking_map.get(safeInt(line['id']))
            ))

        return lines

    def prepare_shipping_lines(self, data, order):
        lines = []
        for shipping_line in data.get('shipping_lines'):
            lines.append(ShopifyOrderShippingLine(
                store=order.store,
                order=order,
                shipping_line_id=shipping_line['id'],
                price=shipping_line['price'],
                title=shipping_line['title'],
                code=shipping_line['code'],
                source=shipping_line['source'],
                phone=shipping_line['phone'],
                carrier_identifier=shipping_line['carrier_identifier'],
                requested_fulfillment_service_id=shipping_line['requested_fulfillment_service_id']
            ))

        return lines
