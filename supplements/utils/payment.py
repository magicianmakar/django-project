from collections import defaultdict

from django.db.transaction import atomic
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.text import Truncator

from commercehq_core.models import CommerceHQStore
from groovekart_core.models import GrooveKartStore
from leadgalaxy.models import ShopifyStore
from shopified_core.shipping_helper import country_from_code
from supplements.lib.authorizenet import charge_customer_profile
from supplements.models import PLSOrder, PLSOrderLine
from woocommerce_core.models import WooStore


def complete_payment(transaction_id, pls_order_id):
    """
    This function is suppposed to run in a queue.
    """
    pls_order = PLSOrder.objects.get(id=pls_order_id)
    pls_order.status = pls_order.PAID
    pls_order.payment_date = timezone.now()
    pls_order.stripe_transaction_id = transaction_id
    pls_order.save()
    return pls_order


class Util:
    def __init__(self):
        self.order_cache = {}
        self.product_cache = {}

    def make_payment(self, order_info, lines, user):
        order_number, order_id = order_info
        store_id = self.store.id
        store_type = self.store.store_type

        get_shipstation_line_key = PLSOrderLine.get_shipstation_key

        wholesale_price = amount = 0
        for line in lines:
            user_supplement = line['user_supplement']
            quantity = int(line['quantity'])
            line_amount = user_supplement.cost_price * quantity
            line_wholesale = user_supplement.wholesale_price * quantity
            amount += line_amount
            wholesale_price += line_wholesale

        amount = int(amount * 100)
        wholesale_price = int(wholesale_price * 100)

        sale_price = sum([float(i['price']) * int(i['quantity']) for i in lines])
        sale_price = sale_price * 100

        with atomic():
            pls_order = PLSOrder.objects.create(
                order_number=order_number,
                store_type=store_type,
                store_id=store_id,
                store_order_id=order_id,
                amount=amount,
                sale_price=sale_price,
                wholesale_price=wholesale_price,
                user=user,
            )

            auth_net_lines = []

            for line in lines:
                line_id = line['id']
                user_supplement = line['user_supplement']
                label = user_supplement.current_label
                item_price = int(float(line['price']) * 100)
                quantity = line['quantity']

                key = get_shipstation_line_key(store_type,
                                               store_id,
                                               order_id,
                                               line_id)

                line_amount = int(user_supplement.cost_price * 100)
                wholesale_price = int(user_supplement.wholesale_price * 100)

                PLSOrderLine.objects.create(
                    store_type=store_type,
                    store_id=store_id,
                    store_order_id=order_id,
                    line_id=line_id,
                    shipstation_key=key,
                    pls_order=pls_order,
                    label=label,
                    sale_price=item_price,
                    amount=line_amount,
                    quantity=quantity,
                    wholesale_price=wholesale_price,
                )

                auth_net_lines.append(dict(
                    line_id=line_id,
                    name=Truncator(user_supplement.title).chars(27),
                    quantity=quantity,
                    unit_price=line_amount,
                ))

            auth_net_customer = user.authorize_net_customer
            transaction_id = charge_customer_profile(
                amount,
                auth_net_customer.customer_id,
                auth_net_customer.payment_id,
                auth_net_lines,
            )

            # TODO: Add to queue.
            pls_order = complete_payment(transaction_id, pls_order.id)
            return pls_order

    def get_order(self, order_id):
        order_cache = self.order_cache

        if order_id in order_cache:
            return order_cache[order_id]

        order_cache[order_id] = order = self.store.get_order(order_id)
        return order

    def prepare_data(self, order_data_ids):
        line_items = defaultdict(list)
        effective_order_data_ids = defaultdict(list)
        orders = {}
        errors = 0
        store_type = self.store.store_type

        for order_data_id in order_data_ids:
            try:
                store_id, order_id, line_id = order_data_id.split('_')
            except ValueError:
                errors += 1
                continue

            line_id = int(line_id)

            if PLSOrderLine.exists(store_type,
                                   store_id,
                                   order_id,
                                   line_id):
                continue

            order = self.get_order(order_id)
            orders[order_id] = order

            address = order['shipping_address']
            address['country'] = country_from_code(address['country_code'], address['country'])

            for line_item in order['line_items']:
                if str(line_item['id']) != str(line_id):
                    continue

                product_id = line_item['product_id']
                product = self.product_cache.get(product_id)
                if not product:
                    product = self.store.get_product(product_id)
                    self.product_cache[product_id] = product
                else:
                    # Some data is retrieved from pl_supplement. Due to
                    # caching, if that data is changed, we will get stale data
                    # without refreshing from DB.
                    product.user_supplement.pl_supplement.refresh_from_db()

                if not product.user_supplement.is_approved:
                    continue

                line_item['sku'] = product.user_supplement.shipstation_sku
                label = product.user_supplement.current_label
                line_item['user_supplement'] = product.user_supplement
                line_item['label'] = label
                line_items[order_id].append(line_item)
                effective_order_data_ids[order_id].append(order_data_id)

        return orders, line_items, effective_order_data_ids, errors

    def get_store(self, store_id, store_type):
        if store_type == 'shopify':
            return ShopifyStore.objects.get(id=store_id)
        elif store_type == 'chq':
            return CommerceHQStore.objects.get(id=store_id)
        elif store_type == 'gkart':
            return GrooveKartStore.objects.get(id=store_id)
        elif store_type == 'woo':
            return WooStore.objects.get(id=store_id)

    def mark_label_printed(self, line_id):
        line_item = get_object_or_404(PLSOrderLine, id=line_id)
        line_item.mark_printed()
        return line_item
