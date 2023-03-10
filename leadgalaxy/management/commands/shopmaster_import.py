import csv
import json
from urllib.parse import parse_qs, urlparse
from collections import defaultdict

import arrow
import requests

from leadgalaxy import tasks
from leadgalaxy.utils import get_shopify_product
from product_alerts.utils import parse_supplier_sku, get_supplier_variants
from shopified_core import permissions
from shopified_core.commands import DropifiedBaseCommand
from shopified_core.utils import get_domain, remove_link_query
from shopified_core.models_utils import get_store_model, get_supplier_model, get_product_model

import openpyxl


class ImportException(Exception):
    pass


class Command(DropifiedBaseCommand):

    def add_arguments(self, parser):
        parser.add_argument('--no-progress', dest='progress', action='store_false', help='Show progress')
        parser.add_argument('--store', action='store', type=int, required=True, help='Import to this store')
        parser.add_argument('--store_type', action='store', type=str, required=True, choices=['shopify', 'chq', 'woo'], help='Import to this store')
        parser.add_argument('--shopify-check', action='store_true', help='Check if shopify product exists')
        parser.add_argument('--shopify-duplicate', action='store_true', help='Delete duplicate found products')
        parser.add_argument('--skip', type=int, default=0, help='Number of entries to skip')
        parser.add_argument('--supplier-date', type=str, action='store', help='Change suppliers updated/created before specific date (isoformat)')
        parser.add_argument('--match-supplier-variants', action='store_true', help='Call price monitor app to match supplier variants')
        parser.add_argument('data_file', type=str)

    def start_command(self, progress, store, store_type, data_file, shopify_check, shopify_duplicate, skip, supplier_date, *args, **options):
        self.find_store(store, store_type)

        self.write(f'Importing product for {self.store.title} {self.store.user.email}')

        self.before_supplier = arrow.get(supplier_date) if supplier_date else False
        self.import_counter = 0
        self.last_product = None
        self.shopify_check = store_type == 'shopify' and shopify_check
        self.shopify_duplicate = self.shopify_check and shopify_duplicate
        self.suppliers_mapping = defaultdict(dict)
        self.match_supplier_variants = options.get('match_supplier_variants')

        self.last_supplier_id = None
        self.last_supplier_variants = {}

        file_data = list(self.load_data(data_file))

        if progress:
            self.progress_total(len(file_data))
        else:
            self.write(f'Import {len(file_data)} products')

        for i in file_data:
            self.progress_update()

            if skip > 0:
                skip -= 1
                continue

            self.import_product(store_type, i)
            self.import_counter += 1

        self.progress_close()
        self.progress_total(len(self.suppliers_mapping))

        for product, suppliers in self.suppliers_mapping.items():
            self.progress_update()
            for supplier, mapping in suppliers.items():
                product.set_variant_mapping(mapping, supplier=supplier)

    def load_data(self, data_file):
        ext = data_file.split('.').pop().lower()

        if ext == 'csv':
            for i in csv.DictReader(open(data_file)):
                yield i
        elif ext == 'xlsx':
            wb = openpyxl.load_workbook(filename=data_file, data_only=True)
            ws = wb[list(wb.sheetnames).pop()]

            first_row = True
            column_names = []

            for r in ws.rows:
                row_value = {}
                col_index = 0
                for c in r:
                    if first_row:
                        column_names.append(c.value)
                    else:
                        row_value[column_names[col_index]] = c.value

                    col_index += 1

                if not first_row:
                    yield row_value
                else:
                    first_row = False
        else:
            raise Exception(f'Unsupported file format: {ext}')

    def find_store(self, store, store_type):
        self.store = get_store_model(store_type).objects.get(id=store)
        return self.store

    def import_product(self, store_type, info):
        shopify_id = info['productId']
        supplier_url = info['sourceUrl']
        title = info['title']

        supplier = None

        if shopify_id and supplier_url:
            self.progress_description(f'Importing {shopify_id}...')
            try:
                self.last_product = self.import_shopify(store_type, self.store, shopify_id, supplier_url, title)
                supplier = self.last_product.default_supplier

                self.progress_description(f'Imported to {supplier.id}')
            except KeyboardInterrupt:
                raise
            except ImportException as e:
                self.write(f'Import error: {str(e)}')

        elif supplier_url and self.last_product:
            if self.before_supplier:
                self.progress_description(f'Finding Supplier {supplier_url}...')
                supplier = get_supplier_model(store_type).objects.filter(
                    store=self.last_product.store,
                    product=self.last_product,
                    product_url=supplier_url,
                ).first()

            if not supplier:
                self.progress_description(f'Importing Supplier {supplier_url}...')
                supplier = get_supplier_model(store_type).objects.create(
                    store=self.last_product.store,
                    product=self.last_product,
                    product_url=supplier_url,
                    supplier_name='Supplier',
                    supplier_url='https://www.aliexpress.com/'
                )

        if self.last_product and info.get('productVarId') and info.get('sourceVarId'):
            if not supplier:
                if self.last_product:
                    supplier = self.last_product.default_supplier

            if supplier:
                if supplier.variants_map and 'image' in supplier.variants_map:
                    return False

                if supplier not in self.suppliers_mapping[self.last_product]:
                    self.suppliers_mapping[self.last_product][supplier] = {}

                if self.match_supplier_variants and supplier.get_source_id() \
                        and supplier.get_source_id() != self.last_supplier_id:
                    self.last_supplier_id = supplier.get_source_id()
                    self.last_supplier_variants = get_supplier_variants(supplier.supplier_type(), supplier.get_source_id(), from_api=True)

                self.suppliers_mapping[self.last_product][supplier][info['productVarId']] = self.format_sku(info['sourceVarId'])

    def import_shopify(self, store_type, store, shopify_id, supplier_url, title):
        is_shopify = store_type == 'shopify'
        user = store.user

        can_add, total_allowed, user_count = permissions.can_add_product(user.models_user, ignore_daily_limit=True)
        if not can_add:
            raise ImportException(f'Your current plan allows up to {total_allowed} saved product(s). Currently you have {user_count} saved products.')

        shopify_product = None
        if self.shopify_check:
            try:
                shopify_product = get_shopify_product(store, shopify_id, raise_for_status=True)
            except KeyboardInterrupt:
                raise
            except:
                self.write(f'Product not found: {shopify_id}. Trying to find it using: {title}')
                if title:
                    product_ids = store.gql.find_products_by_title(title, exact_match=True).split(',')
                    if product_ids and len(product_ids) == 1 and '123' not in product_ids:
                        self.write(f'\t> Product ID changed from {shopify_id} to {product_ids[0]}')
                        shopify_id = product_ids[0]
                    elif product_ids and 2 <= len(product_ids) <= 4:
                        self.write(f'\t> Delete duplicates {product_ids}')
                        shopify_id = self.remove_duplicates(product_ids)
                    else:
                        self.write(f'\t> Product search didn\'t return correct results ({len(product_ids)} | {product_ids})')
                        raise ImportException('Product missing')
                else:
                    self.write('\t> Product title is empty')
                    raise ImportException('Product missing and without title')

        product = None

        filter_kwargs = {'store': store}
        if is_shopify:
            filter_kwargs['shopify_id'] = shopify_id
        else:
            filter_kwargs['source_id'] = shopify_id

        found_products = get_product_model(store_type).objects.filter(**filter_kwargs)
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

        supplier_url = remove_link_query(supplier_url)

        if not product:
            product = get_product_model(store_type)(
                **filter_kwargs,
                user=user.models_user,
                data=json.dumps({
                    'title': 'Importing...',
                    'variants': [],
                    'original_url': supplier_url
                })
            )

            permissions.user_can_add(user, product)

            product.save()

        supplier = None
        if self.before_supplier:
            supplier = product.default_supplier

        if not supplier:
            supplier = get_supplier_model(store_type).objects.create(
                store=product.store,
                product=product,
                product_url=supplier_url,
                supplier_name='Supplier',
                supplier_url=f'https://{get_domain(supplier_url, full=True)}/',
                is_default=True
            )

        product.set_default_supplier(supplier, commit=True)

        if is_shopify:
            tasks.update_shopify_product.apply_async(
                args=[store.id, product.shopify_id],
                kwargs={'product_id': product.id, 'shopify_product': shopify_product},
                countdown=self.import_counter * 0.5)
        else:
            try:
                product.sync()

            except KeyboardInterrupt:
                raise

            except:
                product.delete()
                raise ImportException('Product sync error')

        return product

    def format_sku(self, original_sku):
        sku = []
        options = None

        # Price monitor app has better names for each variant
        if self.match_supplier_variants:
            option_ids = ','.join(sorted([o['option_id'] for o in parse_supplier_sku(original_sku)]))
            for v in self.last_supplier_variants:
                variant_ids = ','.join(sorted(v['variant_ids'].split(',')))
                if option_ids == variant_ids:
                    options = parse_supplier_sku(v['sku'])
                    break

        if options is None:
            options = parse_supplier_sku(original_sku)

        for key, item in enumerate(options):
            sku.append({
                'title': item['option_title'].strip(),
                'sku': f"{item['option_group']}:{item['option_id']}"
            })
        return json.dumps(sku)

    def remove_duplicates(self, product_ids):
        for product_id in product_ids[1:]:
            self.write(f'\t\t> Deleting {product_id}')
            rep = requests.delete(url=self.store.api('products', product_id))
            rep.raise_for_status()

        return product_ids[0]
