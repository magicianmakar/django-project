from django.core.management.base import BaseCommand
from django.db import transaction

from leadgalaxy.models import ShopifyProduct


class Command(BaseCommand):
    help = 'Transfers original data from products to the data store'

    def handle(self, *args, **options):
        self.write_success('Starting...')
        products = ShopifyProduct.objects.filter(original_data_key=None)[:10000]
        self.write_success('Transferring {} product(s).'.format(products.count()))
        for product in products:
            self.write_success('Transferring product with ID: {}'.format(product.id))
            with transaction.atomic():
                product.set_original_data(product.original_data)
            self.write_success('Transfer successful.')
        self.write_success('Done.')

    def write_success(self, message):
        self.stdout.write(self.style.MIGRATE_SUCCESS(message))
