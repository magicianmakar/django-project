# -*- coding: utf-8 -*-
import arrow
import time

from shopified_core.management import DropifiedBaseCommand
from django.db.models import Count
from django.utils.timesince import timesince

from leadgalaxy.models import ShopifyProduct
from leadgalaxy.utils import get_domain


class Command(DropifiedBaseCommand):
    help = 'Show product catalog for each store'

    def add_arguments(self, parser):
        parser.add_argument(
            '--store', dest='store', action='store', type=int,
            help='Fulfill orders for the given store')

        parser.add_argument(
            '--date', dest='date', action='store', type=str, default=None,
            help='Get products sold after this date (YYYY-MM-DD)')

        parser.add_argument(
            '--domains', dest='domains', action='store', type=str, default=None,
            help='Get only product orders from specific domains. Ex: --domains=amazon,ebay,aliexpress')

    def start_command(self, *args, **options):
        start = time.time()
        # Create base filter with indexed fields first
        base_filter = {}
        date = options.get('date')
        if date is not None:
            date = arrow.get(date).datetime
            base_filter['shopifyorderline__order__created_at__gte'] = date

        # We need how many times the product was sold and its url
        base_filter["default_supplier__isnull"] = False
        base_filter["default_supplier__gt"] = 0
        base_queryset = ShopifyProduct.objects.filter(**base_filter) \
            .values('default_supplier__supplier_url', 'default_supplier__supplier_name', 'store_id', 'store__title') \
            .annotate(count=Count('shopifyorderline')) \
            .distinct() \
            .order_by('store_id')  # Removes order by created_at

        # Only arg defined store or all
        store = options.get('store')
        if store is not None:
            base_queryset = base_queryset.filter(store_id=store)

        product_catalogs = {}
        catalogs = base_queryset.filter(count__gt=0)

        # Parse each row's domain
        current_store_id = None
        store_title = None
        for catalog in catalogs:
            if current_store_id is None:
                current_store_id = catalog['store_id']
                store_title = catalog['store__title']

            # With the queryset order by store id, print everytime it changes
            if current_store_id != catalog['store_id']:
                self.show_catalog_for_store(store_title, product_catalogs)
                current_store_id = catalog['store_id']
                store_title = catalog['store__title']
                product_catalogs = {}

            url = catalog['default_supplier__supplier_url']
            if url is None:
                supplier_domain = catalog['default_supplier__supplier_name'].lower()
            else:
                if url.startswith('//'):
                    url = 'http:{}'.format(url)

                supplier_domain = get_domain(url)

            count = catalog['count'] or 0
            product_catalogs[supplier_domain] = product_catalogs.get(supplier_domain, 0) + count

        self.show_catalog_for_store(store_title, product_catalogs)

        if date:
            self.write(u'\nOver the past {}'.format(timesince(date)), self.style.WARNING)
        else:
            self.write('\nSince the beginning of time', self.style.WARNING)

        elapsed = time.time() - start
        elapsed = '{:.2f} seconds'.format(elapsed) if elapsed < 60 else '{:.2f} minutes'.format(elapsed / 60)
        self.write(u'\nTime elapsed: {}'.format(elapsed), self.style.ERROR)

    def show_catalog_for_store(self, store_title, product_catalogs):
        self.write('For store: {}'.format(store_title), self.style.WARNING)
        for supplier_domain, line_items_count in product_catalogs.items():
            if supplier_domain is None:
                print supplier_domain
            self.write('{:3,} line items connected to {}'.format(
                line_items_count,
                supplier_domain.title()),
                self.style.MIGRATE_SUCCESS)
