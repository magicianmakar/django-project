from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth.models import User
from django.utils import timezone
from django.db import IntegrityError, transaction

from leadgalaxy.models import *
from leadgalaxy import utils

class Command(BaseCommand):
    def add_arguments(self, parser):
        pass

    def handle(self, *args, **options):
        self.stdout.write(self.style.HTTP_INFO('* Get Orders Fulfillment Status'))

        orders = ShopifyOrder.objects.filter(shopify_status='').exclude(store=None).order_by('store')

        self.stdout.write(self.style.HTTP_INFO('* Found %d Orders' % orders.count()))

        store_title = ''
        with transaction.atomic():
            for order in orders:
                if store_title != order.store.title:
                    store_title = order.store.title
                    self.stdout.write(self.style.MIGRATE_SUCCESS('Store {}'.format(store_title)))

                try:
                    line = utils.get_shopify_order_line(order.store, order.order_id, order.line_id)
                except Exception as e:
                    self.stdout.write(self.style.ERROR('Exception: {}'.format(repr(e))))
                    self.stdout.write(self.style.ERROR('Order: {} / {}'.format(order.order_id, order.line_id)))

                    continue

                fulfillment_status = line.get('fulfillment_status')
                if not fulfillment_status:
                    fulfillment_status = ''

                self.stdout.write(self.style.MIGRATE_SUCCESS(
                    '{}/{} {}'.format(order.order_id, order.line_id, fulfillment_status)))

                order.shopify_status = line.get('fulfillment_status', '')
                order.save()
