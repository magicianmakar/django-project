import csv
import traceback
from collections import defaultdict

import arrow

from leadgalaxy.utils import aws_s3_upload, random_filename
from shopified_core.management import DropifiedBaseCommand
from shopified_core.utils import using_replica, send_email_from_template
from shopify_orders.models import ShopifyOrder


class Command(DropifiedBaseCommand):

    def add_arguments(self, parser):
        parser.add_argument('--no-progress', dest='progress', action='store_false', help='Show progress')
        parser.add_argument('--days', type=int, default=30, help='Remove stores with inactive number of days.')

    def start_command(self, *args, **options):
        self.write('Loading orders...')

        tracks = using_replica(ShopifyOrder).filter(created_at__gte=arrow.utcnow().replace(days=-int(options['days'])).datetime)

        tracks = tracks.prefetch_related('shopifyorderline_set', 'shopifyorderline_set__product', 'shopifyorderline_set__product__default_supplier',
                                         'shopifyorderline_set__product__default_supplier__product')
        tracks = tracks.only('id', 'created_at')
        tracks = tracks.order_by('created_at')

        self.progress = options['progress']

        if self.progress:
            self.progress_total(tracks.count())

        self.product_count = defaultdict(int)
        self.product_info = {}

        for i in tracks.iterator():
            self.progress_update()
            try:
                for line in i.shopifyorderline_set.all():
                    if line.product and line.product.default_supplier and line.product.default_supplier.source_id:
                        supplier = line.product.default_supplier
                        source_id = f'{supplier.source_id}'
                        self.product_count[source_id] += 1
                        if source_id not in self.product_info:
                            self.product_info[source_id] = {
                                'title': supplier.product.title[:80],
                                'price': supplier.product.price
                            }

            except KeyboardInterrupt:
                break
            except:
                traceback.print_exc()

        filename = f"products_data-{random_filename('.csv')}"
        with open(filename, 'w', newline='') as csvfile:
            fieldnames = ['title', 'url', 'price', 'orders']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()

            for k, v in self.product_count.items():
                writer.writerow({
                    'url': f'https://www.aliexpress.com/item/{k}.html',
                    'title': self.product_info[k]['title'],
                    'price': self.product_info[k]['price'],
                    'orders': v
                })

        url = aws_s3_upload(filename=filename, input_filename=filename)
        send_email_from_template(
            tpl=f'Products Analytics Data has been exported:\n{url}',
            subject='[Dropified] Products Analytics Data',
            recipient='ahmed@dropified.com',
            data={},
            nl2br=True
        )
