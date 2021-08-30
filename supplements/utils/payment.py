import json
from decimal import Decimal

import requests
from django.conf import settings
from django.core.cache import cache
from django.db.models import F
from django.db.transaction import atomic
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.urls import reverse

from lib.exceptions import capture_exception, capture_message
from shopified_core.utils import get_store_api, safe_int, safe_float, dict_val, hash_text
from shopified_core.models_utils import get_store_model
from supplements.lib.shipstation import prepare_shipping_data
from supplements.models import UserSupplement, PLSupplement, PLSOrder, PLSOrderLine, ShippingGroup
from supplements.utils import supplement_customer_address


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


def get_shipping_costs(country_code, province_code, total_weight, default_type=None):
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
        capture_exception()
        return [{'error': f'We are currently not shipping to {country_code}, contact support to know more'}]

    if isinstance(costs, list) and len(costs) > 0:
        default_cost = costs[0]
        for cost in costs:
            if default_type:
                # Select expensive (expedited) or economic (standard) shipping type
                if default_type == 'standard' \
                        and default_cost['shipping_cost'] > cost['shipping_cost']:
                    default_cost = cost

                if default_type == 'expedited' \
                        and default_cost['shipping_cost'] < cost['shipping_cost']:
                    default_cost = cost
            else:
                break

        default_cost['selected'] = True

    return costs


def get_shipping_method(shippings, service=None):
    if not shippings:
        return {}

    for shipping in shippings:
        if shipping.get('service') and shipping['service']['service_code'] == service:
            return shipping
    return shippings[0]


def get_shipping(country_code, province_code, total_weight, shipping_service=None):
    shipping_costs = get_shipping_costs(country_code, province_code, total_weight)
    return get_shipping_method(shipping_costs, shipping_service)


class Util:

    def make_payment(self, order_info, lines, user, order):
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

        ship_to, bill_to = prepare_shipping_data(order)
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
                shipping_address_hash=hash_text(ship_to),
                shipping_address=ship_to,
                billing_address=bill_to,
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

                # deduct inventory on parent DB
                if not pl_supplement.deduct_inventory(quantity):
                    # TODO: probably need to add "out of inventory" warning
                    capture_message(f"Out of inventory for Supplement ID# {pl_supplement.id}")

                pl_supplement.save()

                PLSOrderLine.objects.create(
                    store_type=store_type,
                    store_id=store_id,
                    store_order_id=order_id,
                    line_id=line_id,
                    shipstation_key=key,
                    pls_order=pls_order,
                    title=user_supplement.title,
                    label=label,
                    sale_price=item_price,
                    amount=line_amount,
                    quantity=quantity,
                    wholesale_price=wholesale_price,
                    shipping_service=shipping.get('service', {}).get('service_name'),
                    shipping_service_id=shipping.get('service', {}).get('service_id') or '',
                    sku=line['sku'],  # Product SKU
                )

            auth_net_line = dict(
                id=pls_order.id,
                name=f'Process Order # {pls_order.id}',
                quantity=1,
                unit_price=amount,
            )

            transaction_id, error = user.authorize_net_customer.charge(
                amount,
                auth_net_line,
            )
            if not transaction_id:
                raise Exception(error[0])

            # TODO: Add to queue.
            pls_order = complete_payment(transaction_id, pls_order.id)
            return pls_order

    def create_unpaid_order(self, order, user, shippings):
        total_weight = 0
        wholesale_price = 0
        products_cost = 0
        sale_price = 0
        taxes = 0
        duties = 0
        for item in order['items']:
            quantity = int(item['quantity'])
            products_cost += item['user_supplement'].cost_price * quantity
            wholesale_price += item['user_supplement'].wholesale_price * quantity
            total_weight += item['user_supplement'].pl_supplement.weight * quantity
            sale_price += Decimal(item['price']) * quantity

        shipping_cost = order['selected_shipping']['shipping_cost']
        ship_to, bill_to = prepare_shipping_data(order)

        # Taken from cached taxes, taking too long will throw an error
        # TODO: Handle cache error and ask for a page reload if it happens often
        if order['pay_taxes']:
            taxes = Decimal(order['taxes']['taxes']).quantize(Decimal('.01'))
            duties = Decimal(order['taxes']['duties']).quantize(Decimal('.01'))

        pls_order = PLSOrder.objects.create(
            order_number=order['order_number'],
            store_type=self.store.store_type,
            store_id=self.store.id,
            store_order_id=order['id'],
            amount=int((products_cost + shipping_cost + taxes + duties) * 100),
            sale_price=sale_price * 100,
            wholesale_price=int(wholesale_price * 100),
            shipping_price=int(shipping_cost * 100),
            taxes=int(taxes * 100),
            duties=int(duties * 100),
            user=user,
            status=PLSOrder.PENDING,
            shipping_address_hash=hash_text(ship_to),
            shipping_address=ship_to,
            billing_address=bill_to,
        )

        for item in order['items']:
            shipstation_key = PLSOrderLine.get_shipstation_key(
                self.store.store_type,
                self.store.id,
                order['id'],
                item['id'],
                item['label'].id
            )

            item_price = int(float(item['price']) * 100)
            line_amount = int(item['user_supplement'].cost_price * 100)
            wholesale_price = int(item['user_supplement'].wholesale_price * 100)
            quantity = int(item['quantity'])

            # Throws an error if PositiveIntegerField gets negative on update
            # and force bulk ordering again
            # TODO: properly treat some form of InventoryError in api response
            # because it can happen if another user ran the supplement out of stock
            PLSupplement.objects.filter(
                id=item['user_supplement'].pl_supplement_id
            ).update(
                inventory=F('inventory') - quantity
            )

            PLSOrderLine.objects.create(
                store_type=self.store.store_type,
                store_id=self.store.id,
                store_order_id=order['id'],
                line_id=item['id'],
                shipstation_key=shipstation_key,
                pls_order=pls_order,
                title=item['title'],
                label=item['label'],
                sale_price=item_price,
                amount=line_amount,
                quantity=quantity,
                wholesale_price=wholesale_price,
                shipping_service=order['selected_shipping'].get('service', {}).get('service_name'),
                shipping_service_id=order['selected_shipping'].get('service', {}).get('service_id') or '',
                sku=item['sku'],  # Product SKU
                is_bundled=item.get('is_bundle') or False,
            )

        return pls_order

    def create_payment(self, user, orders):
        payment_items = []
        for order in orders:
            payment_items.append({
                'id': order.id,
                'name': f'Process Order # {order.id}',
                'quantity': 1,
                'amount': Decimal(order.amount / 100).quantize(Decimal('.01'))
            })

        transaction_id, error = user.authorize_net_customer.charge_items(payment_items)
        if not transaction_id:
            raise Exception(error)

        for order in orders:
            order.status = order.PAID
            order.payment_date = timezone.now()
            order.stripe_transaction_id = transaction_id
            order.save()

        return orders

    def get_order_data(self, user, order_data_ids, shippings, pay_taxes):
        models_user = user.models_user
        config_pay_taxes = models_user.get_config('pl_pay_taxes') or False
        StoreApi = get_store_api(self.store.store_type)

        user_supplement_cache = {}
        shipping_mapping = {}
        inventory_mapping = {}
        orders_status = {}
        orders = {}
        for order_data_id in order_data_ids:
            orders_status[order_data_id] = {
                'id': order_data_id,
                'status': 'Awaiting payment',
                'supplements': [],
                'success': True,
            }
            try:
                api_result = StoreApi.get_order_data(None, user, {
                    'order': order_data_id, 'original': '1'})
                order_data = json.loads(api_result.content.decode("utf-8"))
            except:
                orders_status[order_data_id].update({
                    'success': False,
                    'status': 'Unable to find data, please refresh your page',
                })
                capture_exception()
                continue

            orders_status[order_data_id].update(order_data)
            orders_status[order_data_id]['supplement'] = {'title': order_data['title']}
            if order_data['supplier_type'] != 'pls':
                orders_status[order_data_id].update({
                    'success': False,
                    'status': 'Unknown source, please check your variant mappings',
                })
                continue

            existing_items = PLSOrderLine.objects.filter(
                store_type=self.store.store_type,
                store_id=self.store.id,
                store_order_id=order_data['order_id'],
                line_id=order_data['line_id']
            )
            if len(existing_items) > 0:
                for existing_item in existing_items:
                    existing_item.save_order_track()

                orders_status[order_data_id].update({
                    'success': False,
                    'status': 'Item previously paid for',
                    'status_link': reverse('pls:my_order_detail', kwargs={
                        'order_id': existing_items[0].pls_order_id
                    })
                })
                continue

            total_weight = Decimal('0.0')
            total_wholesale = Decimal('0.0')
            shipping_country = order_data['shipping_address']['country']
            shipping_province = order_data['shipping_address']['province']

            # Bundled items can have multiple products
            products = order_data['products'] if order_data.get('is_bundle') else [order_data]
            items = []
            for product in products:
                try:
                    # Prevent querying the database for the same supplement more than once
                    user_supplement = user_supplement_cache.get(product['source_id'])
                    if user_supplement is None:
                        user_supplement = models_user.pl_supplements.select_related(
                            'pl_supplement').get(id=product['source_id'])
                        user_supplement_cache[product['source_id']] = user_supplement
                except UserSupplement.DoesNotExist:
                    orders_status[order_data_id].update({'success': False, 'status': "Product not found"})
                    break

                pl_supplement_id = user_supplement.pl_supplement_id
                product_quantity = safe_int(product['quantity'])
                image_url = user_supplement.current_label.image
                product_weight = Decimal(product['weight'])
                total_weight += product_weight
                total_wholesale += user_supplement.pl_supplement.wholesale_price

                supplement = {
                    'title': user_supplement.title,
                    'price': user_supplement.cost_price,
                    'subtotal': user_supplement.cost_price * product_quantity,
                    'quantity': product_quantity,
                    'image_url': image_url,
                    'weight': product_weight,
                }
                orders_status[order_data_id]['supplements'].append(supplement)

                # Labels must be approved prior to ordering
                if not user_supplement.is_approved:
                    orders_status[order_data_id].update({
                        'success': False,
                        'status': "Fix bundle issue",
                    })
                    supplement.update({
                        'status': "Label not approved",
                        'status_link': reverse('pls:user_supplement', kwargs={
                            'supplement_id': user_supplement.id
                        }),
                    })
                    continue

                # Deleted supplements are not longer supported for ordering
                if user_supplement.is_deleted:
                    orders_status[order_data_id].update({
                        'success': False,
                        'status': "Fix bundle issue",
                    })
                    supplement.update({
                        'status': f"Discontinued Supplement ({user_supplement.pl_supplement_id})",
                    })
                    continue

                # Shallow check for supplement inventory, error is thrown if inventory
                # gets negative once we start ordering
                if inventory_mapping.get(pl_supplement_id) is None:
                    inventory_mapping[pl_supplement_id] = user_supplement.pl_supplement.inventory

                if inventory_mapping[pl_supplement_id] < product_quantity:
                    orders_status[order_data_id].update({
                        'success': False,
                        'status': "Fix bundle issue",
                    })
                    supplement.update({
                        'status': "Out of Stock",
                        'status_link': reverse('pls:user_supplement', kwargs={
                            'supplement_id': user_supplement.id
                        }),
                    })
                    continue

                # Shipping supplements must be allowed to locations
                if shipping_country not in user_supplement.shipping_locations \
                        and shipping_province not in user_supplement.shipping_locations:
                    orders_status[order_data_id].update({
                        'success': False,
                        'status': "Fix bundle issue",
                    })
                    supplement.update({
                        'status': 'Shipping location not supported for this product',
                        'status_link': reverse('pls:user_supplement', kwargs={
                            'supplement_id': user_supplement.id
                        }),
                    })
                    continue

                inventory_mapping[pl_supplement_id] -= product_quantity
                items.append({
                    'order_data_id': order_data_id,
                    'id': order_data['line_id'],
                    'user_supplement': user_supplement,
                    'label': user_supplement.current_label,
                    'title': product.get('title') or user_supplement.title,
                    'sku': user_supplement.shipstation_sku,
                    'image_url': image_url,
                    'quantity': product_quantity,
                    'price': order_data['total'],
                    'is_bundle': order_data.get('is_bundle'),
                })
            else:
                # Define order and shipping only if no errors happen
                order_id = order_data['order_id']
                if not orders.get(order_id):
                    pay_order_taxes = pay_taxes.get(str(order_data['order_id']))
                    if pay_order_taxes is None:
                        pay_order_taxes = config_pay_taxes

                    if not settings.ZONOS_API_KEY:
                        pay_order_taxes = False

                    orders[order_id] = {
                        'id': order_data['order_id'],
                        'order_number': order_data['order_name'],
                        'shipping_service': shippings.get(str(order_data['order_id'])),
                        'shipping_address': order_data['shipping_address'],
                        'total_wholesale': total_wholesale,
                        'pay_taxes': pay_order_taxes,
                        'items': [],
                    }

                if len(items) and items[0]['is_bundle']:
                    total_paid = sum((i['user_supplement'].cost_price * i['quantity']) for i in items)
                    for item in items:
                        item['price'] = Decimal(item['price']) * ((item['user_supplement'].cost_price * item['quantity']) / total_paid)
                        item['price'] = item['price'] / item['quantity']

                if orders_status[order_data_id]['success']:
                    # Initialize shipping mapping for order
                    shipping_mapping.setdefault(order_data['order_id'], {
                        'total_weight': Decimal('0.0'),
                        'country_code': order_data['shipping_address']['country_code'],
                        'province_code': dict_val(order_data['shipping_address'],
                                                  ['province_code', 'province']),
                    })
                    shipping_mapping[order_data['order_id']]['total_weight'] += total_weight
                    orders[order_id]['items'] += items

        # Gather successful order shipping methods to show customer
        order_costs = {'shipping': {}, 'taxes': {}}
        default_shipping_option = models_user.get_config('pl_default_shipping_option')
        for order_id in shipping_mapping:
            order_costs['shipping'][order_id] = get_shipping_costs(
                shipping_mapping[order_id]['country_code'],
                shipping_mapping[order_id]['province_code'],
                shipping_mapping[order_id]['total_weight'],
                default_shipping_option,
            )
            for i in order_costs['shipping'][order_id]:
                i['total_weight'] = shipping_mapping[order_id]['total_weight']

            # Shipping location must be supported by our carrier
            if orders[order_id]['shipping_service']:
                shipping = get_shipping_method(
                    order_costs['shipping'][order_id],
                    orders[order_id]['shipping_service']
                )

                # Selected shipping service will sync with selected in template
                for key, item in enumerate(order_costs['shipping'][order_id]):
                    order_costs['shipping'][order_id][key]['selected'] = False
                    service_code = order_costs['shipping'][order_id][key]['service']['service_code']
                    if service_code == orders[order_id]['shipping_service']:
                        order_costs['shipping'][order_id][key]['selected'] = True

            else:
                shipping = next(s for s in order_costs['shipping'][order_id] if s.get('selected') or s.get('error'))

            if not shipping or shipping.get('error'):
                for item in orders[order_id]['items']:
                    orders_status[item['order_data_id']].update({
                        'success': False,
                        'status': shipping.get('error') or 'Error calculating shipping',
                        'supplements': []
                    })

                # Remove order to prevent processing
                order_costs['taxes'][order_id] = {'disabled': True}
                del order_costs['shipping'][order_id]
                del orders[order_id]
                continue

            shipping['shipping_cost'] = Decimal(shipping['shipping_cost']).quantize(Decimal('0.01'))
            orders[order_id]['selected_shipping'] = shipping

        for order_id in orders:
            order_costs['taxes'][order_id] = self.calculate_taxes(orders[order_id], True)
            order_costs['taxes'][order_id]['pay_taxes'] = orders[order_id].get('pay_taxes', False)
            orders[order_id]['taxes'] = order_costs['taxes'][order_id]

        return orders, orders_status, order_costs

    def calculate_taxes(self, order, only_cached=False):
        if not settings.ZONOS_API_KEY:
            return {'disabled': True}

        address = order['shipping_address']
        if address['country_code'] == 'US':
            return {'duties': 0, 'fees': 0, 'taxes': 0}

        shipping_cost = order['selected_shipping'].get('shipping_cost')
        if not shipping_cost:
            return {'duties': 0, 'fees': 0, 'taxes': 0}

        cache_key = f"{address['country_code']}_{address['zip']}_{order['total_wholesale']}_{shipping_cost}"
        response = cache.get(cache_key, {})
        if only_cached or response:
            return response

        data = {
            'currency': 'USD',
            'items': [{
                'id': i['order_data_id'],
                'amount': str(i['user_supplement'].pl_supplement.wholesale_price),
                'description_retail': i['user_supplement'].description,
                'hs_code': i['user_supplement'].pl_supplement.hs_code,
                'quantity': i['quantity'],
            } for i in order['items']],
            'ship_from_country': 'US',
            'ship_to': {
                'city': address['city'],
                'country': address['country_code'],
                'postal_code': address['zip'],
                'state': address['province_code']
            },
            'shipping': {
                'amount': shipping_cost
            }
        }

        try:
            headers = {'Content-Type': 'application/json', 'serviceToken': settings.ZONOS_API_KEY, 'zonos-version': settings.ZONOS_API_VERSION}
            response = requests.post(settings.ZONOS_API_URL, json=data, headers=headers)
            response.raise_for_status()
            response = response.json()
            cache.set(cache_key, response['amount_subtotal'], timeout=3600)
            return response['amount_subtotal']
        except:
            capture_exception()
            return {}

    def get_store(self, store_id, store_type):
        self.store = get_store_model(store_type).objects.get(id=store_id)
        return self.store

    def mark_label_printed(self, line_id):
        line_item = get_object_or_404(PLSOrderLine, id=line_id)
        line_item.mark_printed()
        return line_item

    def mark_label_not_printed(self, line_id):
        line_item = get_object_or_404(PLSOrderLine, id=line_id)
        line_item.mark_not_printed()
        return line_item
