from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from raven.contrib.django.raven_compat.models import client as raven_client

import time
import requests

from shopify_orders.models import ShopifySyncStatus, ShopifyOrder, ShopifyOrderLine
from shopify_orders.utils import get_customer_name, get_datetime


class Command(BaseCommand):
    help = 'Fetch Orders from Shopify API and store them in the database'

    sync_type = 'orders'
    total_order_fetch = 0  # Number of imported orders since command start

    def add_arguments(self, parser):
        parser.add_argument('--status', dest='sync_status', action='append',
                            type=int, help='Sync Store with the given status')

        parser.add_argument('--reset', dest='reset',
                            action='store_true', help='Delete All Imported Orders and queue stores for re-import')

    def handle(self, *args, **options):
        try:
            self.start_command(*args, **options)
        except:
            raven_client.captureException()

    def start_command(self, *args, **options):
        if options['reset']:
            ShopifyOrder.objects.all().delete()
            ShopifySyncStatus.objects.all().update(sync_status=0)

            self.write_success('Done')
            return

        if not options['sync_status']:
            options['sync_status'] = [0]

        while True:
            try:
                order_sync = ShopifySyncStatus.objects.filter(sync_type=self.sync_type, sync_status__in=options['sync_status']).latest('updated_at')

                if not order_sync:
                    break
            except ShopifySyncStatus.DoesNotExist:
                break

            order_sync.sync_status = 1
            order_sync.save()

            try:
                with transaction.atomic():
                    self.fetch_orders(order_sync.store)

                order_sync.sync_status = 2

            except:
                order_sync.sync_status = 4
                raven_client.captureException(extra={'store': order_sync.store, 'user': order_sync.store.user})

            finally:
                order_sync.save()

            if self.total_order_fetch > 10000:
                break

    def fetch_orders(self, store):
        from math import ceil

        limit = 240
        count = store.get_orders_count(status='any', fulfillment='any', financial='any')

        self.write_success('Import {} Order for: {}'.format(count, store.title))
        if not count:
            return

        self.products_map = store.shopifyproduct_set.exclude(shopify_export=None).values_list('id', 'shopify_export__shopify_id')
        self.products_map = dict(map(lambda a: (a[1], a[0]), self.products_map))

        start = time.time()

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

        self.write_success('Orders imported in {} ms'.format(time.time() - start))


    def import_order(self, data, store):
        customer = data.get('customer', {})
        address = data.get('shipping_address', {})

        order = ShopifyOrder(
            store=store,
            user=store.user,
            order_id=data['id'],
            order_number=data['number'],
            customer_id=customer.get('id', 0),
            customer_name=get_customer_name(customer),
            customer_email=customer.get('email'),
            financial_status=data['financial_status'],
            fulfillment_status=data['fulfillment_status'],
            total_price=data['total_price'],
            note=data.get('note'),
            tags=data['tags'],
            city=address.get('city'),
            zip_code=address.get('zip'),
            country_code=address.get('country_code'),
            created_at=get_datetime(data['created_at']),
            updated_at=get_datetime(data['updated_at']),
            closed_at=get_datetime(data['closed_at']),
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

            l.product_id = self.products_map.get(int(line['product_id']))
            l.save()

    def write_success(self, message):
        self.stdout.write(self.style.MIGRATE_SUCCESS(message))
