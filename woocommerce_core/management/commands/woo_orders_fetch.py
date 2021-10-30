import time

import arrow

from django.db import transaction

from lib.exceptions import capture_exception

from shopified_core.commands import DropifiedBaseCommand
from woocommerce_core.models import (
    WooStore,
    WooSyncStatus,
    WooOrder,
    WooOrderLine,
    WooOrderShippingAddress,
    WooOrderBillingAddress,
)
from woocommerce_core.utils import WooListQuery


class Command(DropifiedBaseCommand):
    help = 'Fetch order data from a WooCommerce store and store them to the database.'
    sync_type = 'orders'

    def add_arguments(self, parser):
        parser.add_argument('--status', dest='sync_status', action='append', type=int, help='Sync stores with the given status.')
        parser.add_argument('--reset', dest='reset', action='store_true', help='Delete imported orders and queue store for re-import.')
        parser.add_argument('--progress', dest='progress', action='store_true', help='Show reset progress.')
        parser.add_argument('--store', dest='store_id', action='append', type=int, help="ID's of WooStores to process.")
        parser.add_argument('--max_orders', dest='max_orders', type=int, help='Only sync stores with the given maximum order count.')

    def reset_stores(self, store_ids, verbose=True):
        if type(store_ids) is not list:
            store_ids = [store_ids]
        for store in store_ids:
            store = WooStore.objects.get(id=store)
            self.write_success(f'Reset Store: {store.title}', show=verbose)
            orders = WooOrder.objects.filter(store=store)
            orders_count = orders.count()
            orders.delete()
            self.write_success(f'Deleted Orders: {orders_count}', show=verbose)
            WooSyncStatus.objects.filter(store_id=store.id).update(sync_status=0, pending_orders=None, elastic=False)

    def start_command(self, *args, **options):
        if options['reset']:
            if options['store_id']:
                self.reset_stores(options['store_id'])
            return

        if not options['sync_status']:
            options['sync_status'] = [0, 6]

        while True:
            try:
                order_sync = WooSyncStatus.objects.filter(sync_type=self.sync_type,
                                                          sync_status__in=options['sync_status'])
                if options.get('max_orders'):
                    order_sync = order_sync.filter(orders_count__lte=options.get('max_orders'))
                if options['store_id']:
                    order_sync = order_sync.filter(store__in=options['store_id'])

                order_sync = order_sync.earliest('updated_at')

                if not order_sync:
                    break

            except WooSyncStatus.DoesNotExist:
                break

            if order_sync.sync_status == 6:
                self.reset_stores(order_sync.store.pk)

            order_sync.sync_status = 1
            order_sync.save()

            try:
                count = WooListQuery(order_sync.store, 'orders').count()
                self.progress_total(count, enable=options['progress'])
                self.fetch_orders(order_sync.store, count)
                order_sync.sync_status = 2
                order_sync.elastic = False  # Orders are not indexed by default
                order_sync.revision = 2  # New imported (or re-imported) orders support Product filters by default
                order_sync.save()
                self.progress_close()
                self.update_pending_orders(order_sync)
            except:
                capture_exception(extra={'store': order_sync.store, 'user': order_sync.store.user})
                self.reset_stores(order_sync.store.pk)
                order_sync.sync_status = 4
                order_sync.save()

    def fetch_orders(self, store, count):
        self.write_success(f'Import {count} Order for: {store.title}')

        if not count:
            return

        self.imported_orders = []
        import_start = time.time()
        page = 1

        while page:
            params = {'page': page, 'per_page': 100}
            r = store.wcapi.get('orders', params=params)
            r.raise_for_status()
            orders = r.json()
            self.process_orders(store, orders)
            self.progress_update(len(orders))
            has_next = 'rel="next"' in r.headers.get('link', '')
            page = page + 1 if has_next else 0

        m, s = divmod(time.time() - import_start, 60)

        self.write_success(f'Orders imported in {int(m)}:{int(s)}')

    def process_orders(self, store, orders_list):
        orders = []
        already_imported = []
        with transaction.atomic():
            for order in orders_list:
                if order['id'] not in self.imported_orders:
                    woo_order = WooOrder(store=store)
                    woo_order.order_id = order['id']
                    woo_order.date_created = arrow.get(order['date_created_gmt']).datetime
                    woo_order.status = order['status']
                    woo_order.customer_id = order['customer_id']
                    woo_order.update_data(order)

                    orders.append(woo_order)
                    self.imported_orders.append(order['id'])
                else:
                    already_imported.append(order['id'])
                    self.write(f"Order #{order['id']} Already Imported", self.style.WARNING)

            if orders:
                WooOrder.objects.bulk_create(orders)
                woo_order_shipping_addresses = []
                woo_order_billing_addresses = []
                woo_order_lines = []

                for order in orders:
                    order_data = order.parsed

                    shipping_data = order_data.get('shipping', {})
                    woo_order_shipping_address = WooOrderShippingAddress(order=order)
                    woo_order_shipping_address.first_name = shipping_data['first_name']
                    woo_order_shipping_address.last_name = shipping_data['last_name']
                    woo_order_shipping_address.company = shipping_data['company']
                    woo_order_shipping_address.address_1 = shipping_data['address_1']
                    woo_order_shipping_address.address_2 = shipping_data['address_2']
                    woo_order_shipping_address.city = shipping_data['city']
                    woo_order_shipping_address.state = shipping_data['state']
                    woo_order_shipping_address.postcode = shipping_data['postcode']
                    woo_order_shipping_address.country = shipping_data['country']
                    woo_order_shipping_address.update_data(shipping_data)

                    woo_order_shipping_addresses.append(woo_order_shipping_address)

                    billing_data = order_data.get('billing', {})
                    woo_order_billing_address = WooOrderBillingAddress(order=order)
                    woo_order_billing_address.first_name = billing_data['first_name']
                    woo_order_billing_address.last_name = billing_data['last_name']
                    woo_order_billing_address.company = billing_data['company']
                    woo_order_billing_address.address_1 = billing_data['address_1']
                    woo_order_billing_address.address_2 = billing_data['address_2']
                    woo_order_billing_address.city = billing_data['city']
                    woo_order_billing_address.state = billing_data['state']
                    woo_order_billing_address.postcode = billing_data['postcode']
                    woo_order_billing_address.country = billing_data['country']
                    woo_order_billing_address.phone = billing_data['phone']
                    woo_order_billing_address.email = billing_data['email']
                    woo_order_billing_address.update_data(billing_data)

                    woo_order_billing_addresses.append(woo_order_billing_address)

                    for line_item in order_data.get('line_items', []):
                        woo_order_line = WooOrderLine(order=order)
                        woo_order_line.line_id = line_item['id']
                        woo_order_line.product_id = line_item.get('product_id')
                        woo_order_line.update_data(line_item)

                        woo_order_lines.append(woo_order_line)

                WooOrderShippingAddress.objects.bulk_create(woo_order_shipping_addresses)
                WooOrderLine.objects.bulk_create(woo_order_lines)
            else:
                self.write('Empty Orders', self.style.WARNING)

    def update_pending_orders(self, order_sync):
        while True:
            order_sync.refresh_from_db()
            order_id = order_sync.pop_pending_orders()

            if not order_id:
                break

            time.sleep(1)
