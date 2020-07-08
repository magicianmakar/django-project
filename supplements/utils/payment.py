import copy
import json
from collections import defaultdict

from django.db.transaction import atomic
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.text import Truncator

from bigcommerce_core.models import BigCommerceStore
from commercehq_core.models import CommerceHQStore
from groovekart_core.models import GrooveKartStore
from leadgalaxy.models import ShopifyStore
from woocommerce_core.models import WooStore

from lib.exceptions import capture_exception
from shopified_core.shipping_helper import country_from_code
from shopified_core.utils import safe_float, get_store_api
from supplements.models import PLSOrder, PLSOrderLine, ShippingGroup


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


def get_shipping_cost(country_code, province_code, total_weight):
    try:
        # getting pls country group
        search_country_provice = f"{country_code}-{province_code}"
        try:
            shipping_group = ShippingGroup.objects.get(slug__iexact=search_country_provice, data__isnull=False)
        except ShippingGroup.DoesNotExist:
            shipping_group = ShippingGroup.objects.get(slug__iexact=country_code, data__isnull=False)

        shipping_data = shipping_group.get_data()

        cost = shipping_data.get('shipping_cost_default')
        shipping_rates = shipping_data.get('shipping_rates', [])
        for shipping_rate in shipping_rates:
            if total_weight >= shipping_rate['weight_from'] \
                    and total_weight < shipping_rate['weight_to']:
                cost = shipping_rate['shipping_cost']
    except:
        cost = False
        capture_exception()
    return cost


class Util:
    def __init__(self):
        self.order_cache = {}
        self.product_cache = {}

    def make_payment(self, order_info, lines, user):
        order_number, order_id, shipping_country_code, shipping_province_code = order_info
        store_id = self.store.id
        store_type = self.store.store_type

        get_shipstation_line_key = PLSOrderLine.get_shipstation_key
        total_weight = 0
        wholesale_price = amount = 0
        for line in lines:
            user_supplement = line['user_supplement']
            quantity = int(line['quantity'])
            line_amount = user_supplement.cost_price * quantity
            line_wholesale = user_supplement.wholesale_price * quantity
            amount += line_amount
            wholesale_price += line_wholesale
            total_weight += user_supplement.pl_supplement.weight * quantity

        shipping_price = get_shipping_cost(shipping_country_code, shipping_province_code, total_weight)
        amount = int((safe_float(amount) + shipping_price) * 100)
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
                shipping_price=int(shipping_price * 100),
                user=user,
            )

            auth_net_lines = []

            for line in lines:
                line_id = line['id']
                label = user_supplement.current_label
                key = get_shipstation_line_key(store_type,
                                               store_id,
                                               order_id,
                                               line_id)
                user_supplement = line['user_supplement']
                pl_supplement = user_supplement.pl_supplement
                quantity = int(line['quantity'])
                item_price = int(float(line['price']) * 100)

                line_amount = int(user_supplement.cost_price * 100) * quantity
                wholesale_price = int(user_supplement.wholesale_price * 100) * quantity
                pl_supplement.inventory -= quantity
                pl_supplement.save()

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

            transaction_id = user.authorize_net_customer.charge(
                amount,
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

    def prepare_data(self, request, order_data_ids):
        line_items = defaultdict(list)
        effective_order_data_ids = defaultdict(list)
        orders = {}
        errors = 0
        store_type = self.store.store_type
        models_user = request.user.models_user
        StoreApi = get_store_api(store_type)

        for order_data_id in order_data_ids:
            try:
                store_id, order_id, line_id = order_data_id.split('_')
            except ValueError:
                errors += 1
                continue

            line_id = int(line_id)
            if PLSOrderLine.exists(store_type, store_id, order_id, line_id):
                continue

            api_result = StoreApi.get_order_data(request, request.user, {'order': order_data_id})
            order_data = json.loads(api_result.content.decode("utf-8"))
            try:
                user_supplement = models_user.pl_supplements.get(id=order_data['source_id'])
            except:
                errors += 1
                continue

            # Can be removed once we validate address sent to shipstation
            # using our own {store_type}_customer_address
            order = self.get_order(order_id)
            orders[order_id] = order

            address = order['shipping_address']
            address['country'] = country_from_code(address['country_code'], address['country'])

            for line_item in order['line_items']:
                if str(line_item['id']) != str(line_id):
                    continue

                if order_data.get('is_bundle'):
                    bundles = []
                    for b_product in order_data['products']:
                        line_item = copy.deepcopy(line_item)
                        try:
                            user_supplement = models_user.pl_supplements.get(id=b_product['source_id'])
                        except:
                            bundles = []
                            errors += 1
                            break

                        if not user_supplement.is_approved:
                            bundles = []
                            break

                        line_item['user_supplement'] = user_supplement
                        line_item['quantity'] = b_product['quantity']
                        line_item['sku'] = user_supplement.shipstation_sku
                        line_item['label'] = user_supplement.current_label
                        line_item['id'] = f"{line_item['id']}|{user_supplement.id}"
                        bundles.append(line_item)

                    if len(bundles) == 0:
                        continue

                    line_items[order_id] += bundles
                else:
                    if not user_supplement.is_approved:
                        errors += 1
                        continue

                    line_item['user_supplement'] = user_supplement
                    line_item['sku'] = user_supplement.shipstation_sku
                    line_item['label'] = user_supplement.current_label
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
        elif store_type == 'bigcommerce':
            return BigCommerceStore.objects.get(id=store_id)

    def mark_label_printed(self, line_id):
        line_item = get_object_or_404(PLSOrderLine, id=line_id)
        line_item.mark_printed()
        return line_item

    def mark_label_not_printed(self, line_id):
        line_item = get_object_or_404(PLSOrderLine, id=line_id)
        line_item.mark_not_printed()
        return line_item
