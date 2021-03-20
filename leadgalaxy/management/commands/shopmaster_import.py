import csv
import json
from urllib.parse import parse_qs, urlparse

import requests

from leadgalaxy import tasks
from leadgalaxy.models import ShopifyProduct, ProductSupplier
from shopified_core import permissions
from shopified_core.management import DropifiedBaseCommand
from shopified_core.utils import get_domain, remove_link_query, get_store_model


class ImportException(Exception):
    pass


class Command(DropifiedBaseCommand):

    def add_arguments(self, parser):
        parser.add_argument('--progress', action='store_true', help='Show progress')
        parser.add_argument('--store', action='store', type=int, required=True, help='Import to this store')
        parser.add_argument('--store_type', action='store', type=str, required=True, choices=['shopify', 'chq', 'woo'], help='Import to this store')
        parser.add_argument('data_file', type=open)

    def start_command(self, progress, store, store_type, data_file, *args, **options):
        self.find_store(store, store_type)

        lines_count = len(data_file.readlines())
        data_file.seek(0)

        if progress:
            self.progress_total(lines_count)
        else:
            self.write(f'Import {lines_count} products')

        reader = csv.DictReader(data_file)

        self.import_counter = 0
        self.last_product = None

        for i in reader:
            self.progress_update()
            self.import_product(i)

            self.import_counter += 1

    def find_store(self, store, store_type):
        self.store = get_store_model(store_type).objects.get(id=store)
        return self.store

    def import_product(self, info):
        shopify_id = info['productId']
        supplier_url = info['sourceUrl']

        if shopify_id and supplier_url:
            try:
                if info['platform'] == 'shopify':
                    self.last_product = self.import_shopify(self.store, shopify_id, supplier_url)
            except ImportException:
                pass

        elif supplier_url and self.last_product:
            ProductSupplier.objects.create(
                store=self.last_product.store,
                product=self.last_product,
                product_url=supplier_url,
                supplier_name='Supplier',
                supplier_url='https://www.aliexpress.com/'
            )

    def import_shopify(self, store, shopify_id, supplier_url):
        user = store.user

        can_add, total_allowed, user_count = permissions.can_add_product(user.models_user, ignore_daily_limit=True)
        if not can_add:
            raise ImportException(f'Your current plan allows up to {total_allowed} saved product(s). Currently you have {user_count} saved products.')

        product = None

        found_products = user.models_user.shopifyproduct_set.filter(store=store, shopify_id=shopify_id)
        if len(found_products):
            if len(found_products) == 1:
                if not found_products[0].have_supplier():
                    product = found_products[0]
                else:
                    return found_products[0]
            else:
                raise ImportException('Product is already imported/connected')

        if get_domain(supplier_url) == 'aliexpress':
            if '/deep_link.htm' in supplier_url.lower():
                supplier_url = parse_qs(urlparse(supplier_url).query)['dl_target_url'].pop()

            if '//s.aliexpress.com' in supplier_url.lower():
                rep = requests.get(supplier_url, allow_redirects=False)
                rep.raise_for_status()

                supplier_url = rep.headers.get('location')
        else:
            raise ImportException('Not an aliexpress product')

        supplier_url = remove_link_query(supplier_url)

        if not product:
            product = ShopifyProduct(
                store=store,
                user=user.models_user,
                shopify_id=shopify_id,
                data=json.dumps({
                    'title': 'Importing...',
                    'variants': [],
                    'original_url': supplier_url
                })
            )

            permissions.user_can_add(user, product)
            product.set_original_data('{}')
            product.save()

        supplier = ProductSupplier.objects.create(
            store=product.store,
            product=product,
            product_url=supplier_url,
            supplier_name='Supplier',
            supplier_url='https://www.aliexpress.com/',
            is_default=True
        )

        product.set_default_supplier(supplier, commit=True)

        tasks.update_shopify_product.apply_async(
            args=[store.id, product.shopify_id],
            kwargs={'product_id': product.id},
            countdown=self.import_counter * 0.5)

        return product
