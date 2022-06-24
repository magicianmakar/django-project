from lib.exceptions import capture_exception
from woocommerce_core.models import WooProduct, WooSupplier
from shopified_core.commands import DropifiedBaseCommand
from supplements.models import UserSupplement


class Command(DropifiedBaseCommand):
    help = 'Automatically sync supplement inventory to woo stores'

    def add_arguments(self, parser):
        parser.add_argument('--store', action='store', type=int, help='Fulfill orders for the given store')

    def start_command(self, *args, **options):
        store = options.get('store')
        try:
            products = WooProduct.objects.filter(woosupplier__product_url__contains='supplement', store__is_active=True).distinct()
            products = products.filter(user_supplement__isnull=False, user_supplement__is_deleted=False,
                                       user_supplement__pl_supplement__is_active=True)
            if store is not None:
                products = products.filter(store=store)

            if products:
                for product in products:
                    self.sync_woo_product_quantities(product)
        except Exception:
            capture_exception()

    def sync_woo_product_quantities(self, product):
        try:
            product_data = product.retrieve()
            if not product.default_supplier:
                return

            if product.default_supplier.supplier_type() == 'pls':
                mapping_config = product.get_mapping_config()
                supplier = ''
                if mapping_config:
                    supplier = mapping_config['supplier']

                if product_data is None:
                    return

                if len(product_data['variants']) > 1:
                    variants_update_endpoint = 'products/{}/variations/batch'.format(product.source_id)
                    if supplier is not None:
                        supplier_mapping = product.get_suppliers_mapping()
                        for i, variant in enumerate(product_data['variants']):
                            vid = variant['id']
                            supplier_source = supplier_mapping.get(str(vid))
                            if supplier_source is not None:
                                supplier_id = supplier_source['supplier']
                                variant_source_id = WooSupplier.objects.get(id=supplier_id).get_source_id()
                                inv = UserSupplement.objects.get(id=variant_source_id).pl_supplement.inventory
                                product_data['variants'][i]['stock_quantity'] = inv
                                product_data['variants'][i]['manage_stock'] = True
                        r = product.store.wcapi.put(variants_update_endpoint, {
                            'update': product_data['variants'],
                        })
                        r.raise_for_status()
                else:
                    product_data['stock_quantity'] = product.default_supplier.user_supplement.pl_supplement.inventory
                    product_data['manage_stock'] = True
                    update_endpoint = 'products/{}'.format(product.source_id)
                    r = product.store.wcapi.put(update_endpoint, product_data)
                    r.raise_for_status()
        except Exception:
            capture_exception()
