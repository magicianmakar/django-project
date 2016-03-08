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

        orders = ShopifyOrder.objects.filter(shopify_status='').exclude(store=None).order_by('store', 'order_id')

        self.stdout.write(self.style.HTTP_INFO('* Found %d Orders' % orders.count()))

        store_title = ''
        self.order = {'id': 0}
        for order in orders:
            if store_title != order.store.title:
                store_title = order.store.title
                self.stdout.write(self.style.MIGRATE_SUCCESS('Store {}'.format(store_title)))

            try:
                shopify_order, line = self.get_order_line(order.store, order.order_id, order.line_id)
            except Exception as e:
                self.stdout.write(self.style.ERROR('Exception: {}'.format(repr(e))))
                self.stdout.write(self.style.ERROR('Order: {} / {}'.format(order.order_id, order.line_id)))

                continue

            fulfillment_status = line.get('fulfillment_status')
            if not fulfillment_status:
                fulfillment_status = ''

            self.stdout.write(self.style.HTTP_INFO(
                '{}/{} {} [Order: {}]'.format(order.order_id, order.line_id, fulfillment_status, shopify_order.get('fulfillment_status', ''))))

            order.shopify_status = line.get('fulfillment_status', '')
            order.save()

    def get_order(self, store, order_id):
        rep = requests.get(store.get_link('/admin/orders/{}.json'.format(order_id), api=True))
        data = rep.json()
        if 'order' in data:
            return data['order']
        else:
            raise Exceprion(rep.text)

    def get_order_line(self, store, order_id, line_id):
        if int(self.order['id']) != int(order_id):
            order = self.get_order(store, order_id)
        else:
            order = self.order
        if order:
            self.order = order
            for line in order['line_items']:
                if int(line['id']) == int(line_id):
                    return order, line

        return None
