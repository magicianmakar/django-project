from lib.exceptions import capture_exception
from bigcommerce_core.models import BigCommerceProduct, BigCommerceSupplier
from shopified_core.commands import DropifiedBaseCommand
from shopified_core.utils import http_excption_status_code
from supplements.models import UserSupplement


class Command(DropifiedBaseCommand):
    help = 'Automatically sync supplement inventory to woo stores'

    def add_arguments(self, parser):
        parser.add_argument('--store', action='store', type=int, help='Fulfill orders for the given store')

    def start_command(self, *args, **options):
        store = options.get('store')
        products = BigCommerceProduct.objects.filter(store=store)
        try:
            products = BigCommerceProduct.objects.filter(bigcommercesupplier__product_url__contains='supplement', store__is_active=True).distinct()
            products = products.filter(user_supplement__isnull=False, user_supplement__is_deleted=False,
                                       user_supplement__pl_supplement__is_active=True)
            if store is not None:
                products = products.filter(store=store)

            if products:
                for product in products:
                    self.sync_bigcommerce_product_quantities(product)
        except Exception:
            capture_exception()

    def sync_bigcommerce_product_quantities(self, product):
        try:
            if not product.default_supplier:
                return

            product_data = product.retrieve()
            if product_data is None:
                return

            if product.default_supplier.supplier_type() == 'pls':
                mapping_config = product.get_mapping_config()
                product_config = ''
                if mapping_config:
                    product_config = mapping_config['supplier']

                if len(product_data['variants']) > 1:
                    product_data['inventory_tracking'] = 'variant'
                    if product_config is not None:
                        supplier_mapping = product.get_suppliers_mapping()
                        for i, variant in enumerate(product_data['variants']):
                            v_id = variant['id']
                            supplier_source = supplier_mapping.get(str(v_id))
                            if supplier_source is not None:
                                supplier_id = supplier_source['supplier']
                                variant_source_id = BigCommerceSupplier.objects.get(id=supplier_id).get_source_id()
                                inv = UserSupplement.objects.get(id=variant_source_id).pl_supplement.inventory
                                product_data['variants'][i]['inventory_level'] = inv
                else:
                    try:
                        qty = product.default_supplier.user_supplement.pl_supplement.inventory
                    except AttributeError:
                        return

                    product_data['inventory_tracking'] = 'product'
                    product_data['inventory_level'] = qty
                    product_data['variants'][0]['inventory_level'] = qty
                    product_data['inventory_tracking'] = 'product'
                try:
                    store = product.store
                    r = store.request.put(
                        url=store.get_api_url('v3/catalog/products/%s' % product.source_id),
                        json=product_data
                    )
                    r.raise_for_status()
                    product.update_data(product_data)
                except Exception as e:
                    if http_excption_status_code(e) not in [401, 402, 403, 404, 429]:
                        capture_exception(extra={
                            'rep': r.text if r else '',
                            'data': product_data,
                        }, tags={
                            'product': product.id,
                            'store': product.store,
                        })
        except Exception:
            capture_exception()
