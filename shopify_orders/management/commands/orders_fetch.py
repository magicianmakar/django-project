from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from raven.contrib.django.raven_compat.models import client as raven_client

import requests

from shopify_orders.models import ShopifySyncStatus, ShopifyOrder, ShopifyOrderLine


class Command(BaseCommand):
    help = 'Fetch Orders from Shopify API and store them in the database'

    sync_type = 'orders'
    total_order_fetch = 0  # Number of imported orders since command start

    def add_arguments(self, parser):
        parser.add_argument('--status', dest='sync_status', action='append',
                            type=int, help='Sync Store with the given status')

    def handle(self, *args, **options):
        try:
            self.start_command(*args, **options)
        except:
            import traceback; traceback.print_exc();
            raven_client.captureException()

    def start_command(self, *args, **options):
        if not options['sync_status']:
            options['sync_status'] = [0]

        for order_sync in ShopifySyncStatus.objects.filter(sync_type=self.sync_type, sync_status__in=options['sync_status']):
            order_sync.sync_status = 1
            order_sync.save()

            try:
                with transaction.atomic():
                    self.fetch_orders(order_sync.store)

                order_sync.sync_status = 2

            except:
                import traceback; traceback.print_exc();
                order_sync.sync_status = 4
                raven_client.captureException(extra={'store': order_sync.store, 'user': order_sync.store.user})

            finally:
                order_sync.save()

            if self.total_order_fetch < 10000:
                break

    def fetch_orders(self, store):
        self.write_success('Fetching order for: {}'.format(store.title))

        from math import ceil

        limit = 240
        count = store.get_orders_count(status='any', fulfillment='any', financial='any')

        self.write_success('Import {} Order for: {}'.format(count, store.title))
        if not count:
            return

        session = requests.session()
        pages = int(ceil(count/float(limit)))
        for page in xrange(1, pages+1):
            rep = session.get(
                url=store.get_link('/admin/orders.json', api=True),
                params={
                    'page': page,
                    'limit': limit,
                    'status': 'any',
                    'fulfillment': 'any',
                    'financial': 'any'
                }
            ).json()

        self.total_order_fetch += len(rep['orders'])

        for order in rep['orders']:
            self.import_order(order, store)

    def import_order(self, data, store):
        customer = data.get('customer', {})
        address = data.get('shipping_address', {})

        products_map = store.user.shopifyproduct_set.values_list('id', 'shopify_export__shopify_id')
        products_map = dict(map(lambda a: (a[1], a[0]), products_map))

        order = ShopifyOrder(
            store=store,
            user=store.user,
            order_id=data['id'],
            order_number=data['number'],
            customer_id=customer.get('id', 0),
            customer_name=u'{} {}'.format(customer.get('first_name'), customer.get('last_name')),
            customer_email=customer.get('email'),
            financial_status=data['financial_status'],
            fulfillment_status=data['fulfillment_status'],
            total_price=data['total_price'],
            note=data.get('note'),
            tags=data['tags'],
            city=address.get('city'),
            zip_code=address.get('zip'),
            country_code=address.get('country_code'),
        )

        order.save()

        for line in data.get('line_items', []):
            l = ShopifyOrderLine(
                order=order,
                line_id=line['id'],
                shopify_product=line['product_id'],
                title=line['title'],
                price=line['price'],
                quantity=line['quantity'],
                variant_id=line['variant_id'],
                variant_title=line['variant_title'])

            l.product_id = products_map.get(int(order.order_id))
            l.save()

    def write_success(self, message):
        self.stdout.write(self.style.MIGRATE_SUCCESS(message))
