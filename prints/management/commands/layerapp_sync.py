from shopified_core.commands import DropifiedBaseCommand

from prints.models import Product, Category
from prints.utils import LayerApp, import_layerapp_product


class Command(DropifiedBaseCommand):
    help = 'Sync LayerApp products and categories'

    def start_command(self, *args, **options):
        layer_app = LayerApp()
        for api_category in layer_app.get_categories():
            category, created = Category.objects.get_or_create(
                source_type='layerapp',
                source_id=api_category.get('id')
            )
            category.title = api_category.get('name')
            category.save()

        for api_product in layer_app.get_products():
            product_id = api_product.get('id')
            product, created = Product.objects.get_or_create(
                source_type='layerapp',
                source_id=product_id
            )

            import_layerapp_product(product, api_product, verbosity=options.get('verbosity', 1))
