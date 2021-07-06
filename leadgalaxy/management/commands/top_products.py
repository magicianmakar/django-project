import csv
import traceback
from collections import defaultdict

import arrow

from leadgalaxy.utils import aws_s3_upload, random_filename
from shopified_core.commands import DropifiedBaseCommand
from shopified_core.utils import using_replica, send_email_from_template
from shopify_orders.models import ShopifyOrder


class Command(DropifiedBaseCommand):

    def add_arguments(self, parser):
        parser.add_argument('--no-progress', dest='progress', action='store_false', help='Show progress')
        parser.add_argument('--days', type=int, default=30, help='Remove stores with inactive number of days.')

    def start_command(self, *args, **options):
        self.write('Loading orders...')

        early_id = using_replica(ShopifyOrder).filter(created_at__gte=arrow.utcnow().replace(days=-int(options['days'])).datetime)[0].id

        tracks = using_replica(ShopifyOrder).filter(id__gte=early_id)
        tracks = tracks.prefetch_related('shopifyorderline_set', 'shopifyorderline_set__product', 'shopifyorderline_set__product__default_supplier',
                                         'shopifyorderline_set__product__default_supplier__product')

        tracks = tracks.only('id', 'created_at')
        tracks = tracks.order_by('id')

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
                                'price': supplier.product.price,
                                'store': line.product.store_id,
                                'user': line.product.user_id
                            }

            except KeyboardInterrupt:
                break
            except:
                traceback.print_exc()

        filename = f"products_data-{random_filename('.csv')}"
        with open(filename, 'w', newline='') as csvfile:
            fieldnames = ['title', 'url', 'store', 'user', 'price', 'orders']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()

            # for k, v in self.product_count.items():
            top_count = 200
            for k, v in sorted(self.product_count.items(), key=lambda item: item[1], reverse=True):
                writer.writerow({
                    'url': f'https://www.aliexpress.com/item/{k}.html',
                    'title': self.product_info[k]['title'],
                    'price': self.product_info[k]['price'],
                    'store': self.product_info[k]['store'],
                    'user': self.product_info[k]['user'],
                    'orders': v
                })

                top_count -= 1

                if not top_count:
                    break

        url = aws_s3_upload(filename=filename, input_filename=filename)
        send_email_from_template(
            tpl=f'Products Analytics Data has been exported <a href="{url}">Download</a>',
            subject='[Dropified] Products Analytics Data',
            recipient='ahmed@dropified.com',
            data={},
        )
