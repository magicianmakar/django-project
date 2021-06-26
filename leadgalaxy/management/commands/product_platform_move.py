from django.contrib.auth.models import User

from shopified_core.management import DropifiedBaseCommand
from shopified_core.models_utils import get_product_model, get_supplier_model
from shopified_core.utils import safe_int


class Command(DropifiedBaseCommand):
    help = 'Auto fulfill tracked orders with a tracking number and unfulfilled status'

    def add_arguments(self, parser):
        parser.add_argument('--user', action='store', type=str, required=True, help='User ID or email')
        parser.add_argument('--from', action='store', type=str, required=True, choices=['shopify', 'chq', 'woo'], help='Move products from')
        parser.add_argument('--to', action='store', type=str, required=True, choices=['shopify', 'chq', 'woo'], help='Move products to this platform')

    def start_command(self, **options):
        user = None

        try:
            if safe_int(options['user']):
                user = User.objects.get(id=safe_int(options['user']))
            else:
                user = User.objects.get(email=options['user'])
        except User.DoesNotExist:
            self.write(f"No user found with id/email: {options['user']}")
        except User.MultipleObjectsReturned:
            self.write(f"Multiple user found with email: {options['user']}")
            for u in User.objects.filter(email=options['user']):
                self.write(f'\t ID: {u.id} Plan: {u.profile.plan.title}')
        finally:

            if not user:
                return

        self.write(f"Move products from {options['from']} to {options['to']} for user {user.email}")

        products = get_product_model(options['from']).objects.filter(user=user)
        if options['from'] == 'shopify':
            products = products.filter(shopify_id=0)
        else:
            products = products.filter(source_id=0)

        self.write(f'Found {products.count()} products')

        for product in products:
            new_product = self.copy_product(get_product_model(options['to']), product)

            self.write(f'Product Created: {new_product.id}')

            self.copy_suppliers(get_supplier_model(options['to']), product, new_product)

        if input('Delete original products? [y/N] ') == 'y':
            self.write('Deleting original products...')
            products.delete()

    def copy_product(self, model, product):
        new_product = model()
        new_product.user = product.user
        new_product.from_json(product.to_json())
        new_product.save()

        return new_product

    def copy_suppliers(self, model, product, new_product):
        suppliers = product.get_suppliers()
        for supplier in suppliers:
            new_supplier = model()
            new_supplier.store = new_product.store
            new_supplier.product = new_product

            new_supplier.product_url = supplier.product_url
            new_supplier.supplier_name = supplier.supplier_name
            new_supplier.supplier_url = supplier.supplier_url

            try:
                new_supplier.source_id = supplier.source_id
            except:
                pass

            new_supplier.is_default = supplier.is_default
            new_supplier.created_at = supplier.created_at

            new_supplier.save()

            if new_supplier.is_default or len(suppliers) == 1:
                new_product.set_default_supplier(new_supplier)
