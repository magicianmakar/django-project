import json
from collections import defaultdict

from django.db.transaction import atomic
from django.shortcuts import get_object_or_404
from django.utils import timezone

from lib.exceptions import capture_exception
from shopified_core.shipping_helper import country_from_code
from shopified_core.utils import get_store_api, safe_float, get_store_object
from supplements.models import PLSOrder, PLSOrderLine, ShippingGroup
from supplements.utils import supplement_customer_address


def complete_payment(transaction_id, pls_order_id):
    """
    This function is suppposed to run in a queue.
    """
    pls_order = PLSOrder.objects.get(id=pls_order_id)
    # TODO: AUTHNET ROLLBACK uncomment below
    # assert transaction_id, 'Payment processing failed'
    if transaction_id:
        pls_order.status = pls_order.PAID
        pls_order.payment_date = timezone.now()
        pls_order.stripe_transaction_id = transaction_id
        pls_order.save()
    return pls_order


def get_shipping_costs(country_code, province_code, total_weight):
    try:
        address = supplement_customer_address({'country_code': country_code})
        country_code = address['country_code']

        # getting pls country group
        search_country_provice = f"{country_code}-{province_code}"
        try:
            shipping_group = ShippingGroup.objects.get(slug__iexact=search_country_provice, data__isnull=False)
        except ShippingGroup.DoesNotExist:
            shipping_group = ShippingGroup.objects.get(slug__iexact=country_code, data__isnull=False)

        shipping_data = shipping_group.get_data()

        costs = []
        services = {s['service_id']: s for s in shipping_data.get('services', [])}
        shipping_rates = shipping_data.get('shipping_rates', [])
        for shipping_rate in shipping_rates:
            if total_weight >= shipping_rate['weight_from'] \
                    and total_weight < shipping_rate['weight_to']:
                if shipping_rate.get('service_id'):
                    shipping_rate['service'] = services.get(shipping_rate.get('service_id'))

                costs.append(shipping_rate)

        if not costs:
            costs.append({'shipping_cost': shipping_data.get('shipping_cost_default')})

    except ShippingGroup.DoesNotExist:
        costs = f'We are currently not shipping to {country_code}, contact support to know more'
        capture_exception()

    except:
        costs = False
        capture_exception()

    return costs


def get_shipping(country_code, province_code, total_weight, shipping_service=None):
    costs = get_shipping_costs(country_code, province_code, total_weight)

    for cost in costs:
        if cost.get('service') and cost['service']['service_code'] == shipping_service:
            return cost

    return costs[0]


class Util:
    def __init__(self):
        self.order_cache = {}
        self.product_cache = {}

    def make_payment(self, order_info, lines, user):
        order_number, order_id, shipping_country_code, shipping_province_code, shipping_service = order_info
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

        shipping = get_shipping(
            shipping_country_code,
            shipping_province_code,
            total_weight,
            shipping_service
        )
        shipping_price = shipping['shipping_cost']
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

            for line in lines:
                line_id = line['id']
                label = line['label']
                key = get_shipstation_line_key(store_type,
                                               store_id,
                                               order_id,
                                               line_id,
                                               label.id)
                user_supplement = line['user_supplement']
                pl_supplement = user_supplement.pl_supplement
                quantity = int(line['quantity'])
                item_price = int(float(line['price']) * 100)

                line_amount = int(user_supplement.cost_price * 100)
                wholesale_price = int(user_supplement.wholesale_price * 100)
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
                    shipping_service=shipping.get('service', {}).get('service_name'),
                    sku=line['sku'],  # Product SKU
                )

            # TODO: AUTHNET ROLLBACK
            transaction_id = None
            # auth_net_line = dict(
            #     id=pls_order.id,
            #     name=f'Process Order # {pls_order.id}',
            #     quantity=1,
            #     unit_price=amount,
            # )

            # transaction_id = user.authorize_net_customer.charge(
            #     amount,
            #     auth_net_line,
            # )

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

            api_result = StoreApi.get_order_data(request, request.user, {'order': order_data_id, 'original': '1'})
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
                        try:
                            user_supplement = models_user.pl_supplements.get(id=b_product['source_id'])
                        except:
                            bundles = []
                            errors += 1
                            break

                        if not user_supplement.is_approved:
                            bundles = []
                            break

                        bundles.append({
                            **line_item,
                            'user_supplement': user_supplement,
                            'label': user_supplement.current_label,
                            'sku': user_supplement.shipstation_sku,
                            'quantity': b_product['quantity'],
                        })

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
        return get_store_object(store_id, store_type)

    def mark_label_printed(self, line_id):
        line_item = get_object_or_404(PLSOrderLine, id=line_id)
        line_item.mark_printed()
        return line_item

    def mark_label_not_printed(self, line_id):
        line_item = get_object_or_404(PLSOrderLine, id=line_id)
        line_item.mark_not_printed()
        return line_item
