import json
from collections import defaultdict

from django.db.transaction import atomic
from django.utils import timezone
from django.views.generic import View

import requests

from leadgalaxy.utils import get_store_from_request
from shopified_core.mixins import ApiResponseMixin
from stripe_subscription.stripe_api import stripe

from .lib.shipstation import create_shipstation_order, prepare_shipstation_data
from .models import Order, OrderLine


def complete_payment(transaction_id, order_id):
    """
    This function is suppposed to run in a queue.
    """
    order = Order.objects.get(id=order_id)
    order.status = order.PAID
    order.payment_date = timezone.now()
    order.stripe_transaction_id = transaction_id
    order.save()
    return order


class ProductCommonApi(ApiResponseMixin, View):
    order_cache = {}

    def make_payment(self, order_info, lines, user, currency, amount):
        order_number, order_id = order_info
        customer = user.stripe_customer.retrieve()
        store_id = self.store.id
        store_type = self.store_type

        get_shipstation_line_key = OrderLine.get_shipstation_key

        with atomic():
            amount = int(amount)
            order = Order.objects.create(
                order_number=order_number,
                store_type=store_type,
                store_id=store_id,
                store_order_id=order_id,
                amount=amount,
                user=user,
            )

            for line_id, sku in lines:
                key = get_shipstation_line_key(store_type,
                                               store_id,
                                               order_id,
                                               line_id)
                OrderLine.objects.create(
                    store_type=store_type,
                    store_id=store_id,
                    store_order_id=order_id,
                    line_id=line_id,
                    sku=sku,
                    shipstation_key=key,
                    order=order,
                )

            response = stripe.Charge.create(
                amount=amount,
                currency=currency,
                customer=customer.id,
                source=customer.default_source,
                description=order_number,
                metadata=dict(
                    order_id=order_id,
                )
            )

            if response['paid']:
                # TODO: Add to queue.
                order = complete_payment(response['id'], order.id)
                return order
            else:
                raise Exception("Payment failed")

    def get_order(self, order_id):
        order_cache = self.order_cache

        if order_id in order_cache:
            return order_cache[order_id]

        store = self.store
        url = store.api('orders', order_id)
        response = requests.get(url)
        order_cache[order_id] = order = response.json()['order']
        return order

    def prepare_data(self, order_data_ids):
        line_items = defaultdict(list)
        effective_order_data_ids = defaultdict(list)
        orders = {}
        errors = 0
        store_type = self.store_type

        for order_data_id in order_data_ids:
            try:
                store_id, order_id, line_id = order_data_id.split('_')
            except ValueError:
                errors += 1
                continue

            line_id = int(line_id)

            if OrderLine.exists(store_type,
                                store_id,
                                order_id,
                                line_id):
                continue

            order = self.get_order(order_id)
            orders[order_id] = order

            for line_item in order['line_items']:
                if line_item['id'] != line_id:
                    continue

                line_items[order_id].append(line_item)
                effective_order_data_ids[order_id].append(order_data_id)

        return orders, line_items, effective_order_data_ids, errors

    def post_make_payment(self, request, user, data):
        self.store = get_store_from_request(request)
        self.store_type = Order.get_store_type(self.store)

        data = json.loads(request.body.decode())
        success = error = 0
        success_ids = []

        info = self.prepare_data(data['order_data_ids'])
        orders, line_items, order_data_ids, error = info

        for order_id, order in orders.items():
            order_info = (order['name'], order_id)
            order_line_items = line_items[order_id]
            amount_orig = sum([float(i['price']) for i in order_line_items])
            amount = int(amount_orig * 100)

            currency = order['currency']
            currency = 'usd'  # TODO: Fix currency.

            lines = [(i['id'], i['sku']) for i in order_line_items]

            try:
                payment_order = self.make_payment(order_info,
                                                  lines,
                                                  user,
                                                  currency,
                                                  amount)
            except Exception as e:
                print(e)
                error += len(lines)
            else:
                shipstation_data = prepare_shipstation_data(payment_order,
                                                            order,
                                                            order_line_items,
                                                            )
                create_shipstation_order(payment_order, shipstation_data)
                success += len(lines)
                success_ids.extend([
                    {'id': i, 'status': payment_order.status_string}
                    for i in order_data_ids[order_id]
                ])

        data = {'success': success, 'error': error, 'successIds': success_ids}
        return self.api_success(data)
