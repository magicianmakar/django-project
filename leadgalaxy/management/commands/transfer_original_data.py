from django.core.management.base import BaseCommand
from django.db import transaction

from leadgalaxy.models import ShopifyProduct

from tqdm import tqdm


class Command(BaseCommand):
    help = 'Transfers original data from products to the data store'

    def add_arguments(self, parser):
        parser.add_argument(
            '--max', dest='max', action='store', required=True, type=int,
            help='Maximuim number of products to migrate')

    def handle(self, *args, **options):

        products = ShopifyProduct.objects.filter(original_data_key=None)[:options['max']]
        total = products.count()

        self.write_success('Transferring {} products'.format(products.count()))

        pbar = tqdm(total=total)

        with transaction.atomic():
            for product in products:
                product.set_original_data(product.original_data, clear_original=True)
                pbar.update(1)

        pbar.close()

        if total < 10:
            self.stdout.write('Products: ')
            self.stdout.write('\n'.join(['\thttps://app.shopifiedapp.com/product/%d' % p.id for p in products]))

        self.write_success('Done')

    def write_success(self, message):
        self.stdout.write(self.style.MIGRATE_SUCCESS(message))
