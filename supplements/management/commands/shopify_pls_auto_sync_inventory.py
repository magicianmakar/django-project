import time

from lib.exceptions import capture_exception
from leadgalaxy import utils
from leadgalaxy.models import ShopifyProduct, ProductSupplier
from shopified_core.commands import DropifiedBaseCommand
from supplements.models import UserSupplement


class Command(DropifiedBaseCommand):
    help = 'Automatically sync supplement inventory to stores'

    def add_arguments(self, parser):
        parser.add_argument('--store', action='store', type=int, help='Fulfill orders for the given store')

    def start_command(self, *args, **options):
        store = options.get('store')
        try:
            # products = ShopifyProduct.objects.filter(user_supplement__isnull=False, user_supplement__is_deleted=False,
            #                                          user_supplement__pl_supplement__is_active=True)

            products = ShopifyProduct.objects.filter(productsupplier__product_url__contains='supplement').distinct()
            if store is not None:
                products = products.filter(store=store)
            if products:
                for product in products:
                    self.sync_shopify_product_quantities(product)
        except Exception:
            capture_exception()

    def sync_shopify_product_quantities(self, product):
        try:
            if not product.default_supplier:
                return

            product_data = utils.get_shopify_product(product.store, product.shopify_id)
            if product_data is None:
                return

            if product.default_supplier.supplier_type() == 'pls':
                mapping_config = product.get_mapping_config()
                supplier_config = ''
                if mapping_config:
                    supplier_config = mapping_config['supplier']

                if len(product_data['variants']) > 1:
                    if supplier_config is not None:
                        supplier_mapping = product.get_suppliers_mapping()
                        for variant in product_data['variants']:
                            v_id = variant['id']
                            supplier_source = supplier_mapping.get(str(v_id))
                            if supplier_source is not None:
                                supplier_id = supplier_source['supplier']
                                variant_source_id = ProductSupplier.objects.get(id=supplier_id).get_source_id()
                                inv = UserSupplement.objects.get(id=variant_source_id).pl_supplement.inventory
                                product.set_variant_quantity(quantity=inv, variant_id=v_id)
                                time.sleep(0.5)
                else:
                    qty = product.default_supplier.user_supplement.pl_supplement.inventory
                    product.set_variant_quantity(quantity=qty, variant=product_data['variants'][0])
                    time.sleep(0.5)
        except Exception:
            capture_exception()
