import json
from decimal import Decimal

from django.db import models
from django.utils import timezone

from leadgalaxy.templatetags.template_helper import money_format
from lib.exceptions import capture_exception, capture_message
from shopified_core import permissions
from shopified_core.mixins import ApiResponseMixin
from shopified_core.models_utils import get_store_model
from shopified_core.shipping_helper import country_from_code
from shopified_core.utils import get_cached_order, safe_int
from stripe_subscription.stripe_api import stripe
from .forms import CarrierForm, WarehouseForm
from .models import (
    Order,
    OrderItem,
    Supplier,
    Warehouse,
    AccountBalance,
    AccountCredit,
)
from .utils import (
    OrderError,
    Address,
    get_logistics_account,
    get_easypost_api,
    get_root_easypost_api,
    get_supplier_listing,
)


class LogisticsApi(ApiResponseMixin):
    http_method_names = ['delete', 'post', 'get']

    def post_shipping(self, request, user, data):
        if not user.can('logistics.use'):
            return self.api_error('Your current plan doesn\'t have this feature.', status=403)

        # TODO: select warehouse before shipping
        warehouse = user.models_user.warehouses.active().first()
        if not warehouse:
            return self.api_error('No warehouses found, please add one', status=404)

        error = None
        warehouses = data.get('warehouses') or {}
        packages = data.get('packages') or {}
        rates = data.get('rates') or {}
        refreshes = data.get('refresh') or {}
        customs_items = data.get('customs_items') or {}
        store_type = data.get('store_type') or 'shopify'
        order_data_ids = data.get('order_data_ids')
        connect_product = data.get('connect_products')

        orders = [o for o in Order.objects.filter(
            items__order_data_id__in=[f"{store_type}_{i.replace('raw_', '')}" for i in data.get('order_data_ids')])]

        for order_data_id in order_data_ids:
            order_data = get_cached_order(user, store_type, order_data_id)[1]
            if order_data is None:
                order_data = get_cached_order(user, store_type, f'raw_{order_data_id}')[1]
                if order_data is None:
                    return self.api_error('Unable to find data, please refresh your page', status=404)

            if order_data.get('supplier_type') and order_data.get('supplier_type') != 'logistics':
                continue

            store = get_store_model(store_type).objects.get(id=order_data['store'])
            if not permissions.user_can_view(user, store):
                return self.api_error('Store not found', status=404)

            order = None
            order_data_id = order_data_id.replace('raw_', '')
            existing_orders = [order for order in orders if f"{store_type}_{order_data_id}" in order.order_data_ids]
            if existing_orders:
                order = existing_orders[0]
                warehouse = order.warehouse

            warehouse_id = int(warehouses.get(order_data_id, 0)) or None
            if warehouse_id:
                warehouse = user.models_user.warehouses.get(id=warehouse_id)

            supplier, listing = get_supplier_listing(store, order_data, warehouse, connect_product=connect_product)
            # TODO: handle inventory
            if listing and listing.inventory is not None:
                pass

            # Logistics orders can be bundled by address to reduce shipping rates
            if not order:
                to_address = Address(user=user, **order_data['logistics_address'])
                for existing_order in orders:
                    match_supplier = supplier is None or existing_order.warehouse_id == supplier.warehouse_id
                    if to_address.hash == existing_order.to_address_hash and match_supplier:
                        order = existing_order
                        break

            if not order:
                to_address = Address(user=user, **order_data['logistics_address'])
                to_address_dict = to_address.create()
                if to_address_dict['errors']:
                    capture_message('3PL Address not found', extra={'easypost_errors': to_address_dict['errors']})
                    to_address_dict['errors'] = ['Address not found or invalid, please check the address is correct']
                order, created = Order.objects.get_or_create(
                    store_type=store_type,
                    store_id=order_data['store'],
                    store_order_number=order_data['order_name'],
                    to_address=json.dumps(to_address_dict),
                    to_address_hash=to_address.hash,
                    from_address=json.dumps(warehouse.logistics_address.to_dict()),
                    warehouse=warehouse,
                )
                orders.append(order)

            order_id = str(order.id)
            package = packages.get(order_id)
            refresh = bool(refreshes.get(order_id))

            to_address = Address(user=user, **{
                **order_data['logistics_address'],
                **order.get_address(),
                **data.get('address', {})
            })
            if to_address.hash != order.to_address_hash:
                to_address_dict = to_address.create()
                if to_address_dict['errors']:
                    capture_message('3PL Address not found', extra={'easypost_errors': to_address_dict['errors']})
                    to_address_dict['errors'] = ['Address not found or invalid, please check the address is correct']
                order.to_address_hash = to_address.hash
                order.to_address = json.dumps(to_address_dict)

            if warehouse_id is not None and order.warehouse_id != warehouse_id:
                order.items.filter(order_data_id=f"{store_type}_{order_data_id}").delete()
                to_address = Address(user=user, **order.get_address())
                if order.items.count() == 0:
                    if order in orders:
                        orders.remove(order)
                    if order.id:
                        order.delete()

                order, created = Order.objects.get_or_create(
                    store_type=store_type,
                    store_id=order_data['store'],
                    store_order_number=order_data['order_name'],
                    to_address=json.dumps(to_address.to_dict()),
                    to_address_hash=to_address.hash,
                    from_address=json.dumps(warehouse.logistics_address.to_dict()),
                    warehouse=warehouse,
                )
                orders.append(order)

            items = OrderItem.objects.filter(
                order=order,
                order_data_id=f"{store_type}_{order_data_id}",
                listing=listing,
            )
            if len(items) > 1:
                items.delete()

            customs_item = customs_items.get(order_data_id) or {}
            OrderItem.objects.update_or_create(
                order=order,
                order_data_id=f"{store_type}_{order_data_id}",
                listing=listing,
                defaults={
                    **customs_item,
                    'unit_cost': order_data['total'],
                    'quantity': order_data['quantity'],
                    'title': order_data['title'],
                }
            )
            if customs_item and customs_item.get('weight') and listing:
                listing.variant.weight = customs_item['weight']
                listing.variant.save()

            address_errors = order.get_address().get('errors')
            if package:
                # TODO: Handle shipment creation errors
                order.pack(package, force=refresh)

            selected_rate = rates.get(order_id)
            if not address_errors and selected_rate and not refresh:
                try:
                    order.pay(selected_rate)

                except OrderError as e:
                    return self.api_error(e.message, status=403)

                except get_root_easypost_api().Error as e:
                    capture_exception()
                    if 'The requested resource could not be found' in str(e):
                        order.pack(package, force=True)
                        error = 'Error contacting carrier, please try again' if not error else error
                    else:
                        raise

            order.save()

        # TODO: Use prefetch related to get only asked items (by order_data_id) for this order
        return self.api_success({
            'error': error,
            'orders': [o.to_dict() for o in Order.objects.filter(
                items__order_data_id__in=[f"{store_type}_{i.replace('raw_', '')}" for i in order_data_ids]
            ).distinct()]
        })

    def get_warehouse(self, request, user, data):
        try:
            warehouse = Warehouse.objects.get(id=data.get('id'), user=user.models_user)
        except Warehouse.DoesNotExist:
            return self.api_error('Warehouse not found', status=404)
        return self.api_success(warehouse.to_dict())

    def post_warehouse(self, request, user, data):
        data = data.copy()
        data['country'] = country_from_code(data['country_code'])
        data['user'] = request.user.models_user.id

        if data.get('id'):
            warehouse = Warehouse.objects.get(id=data.get('id'), user=user.models_user)
            form = WarehouseForm(data, instance=warehouse)
        else:
            form = WarehouseForm(data)

        if form.is_valid():
            warehouse = form.save(commit=False)
            result = warehouse.source_address()
            errors = result.get('errors')
            if not errors:
                warehouse.save()
        else:
            errors = form.errors

        return self.api_success({'errors': errors})

    def delete_warehouse(self, request, user, data):
        warehouse = user.models_user.warehouses.filter(id=data['id']).first()
        if warehouse is None:
            return self.api_error('Warehouse Not Found', status=404)

        if warehouse.products.exists() or warehouse.orders.exists():
            user.models_user.warehouses.filter(id=data['id']).update(deleted_at=timezone.now())
        else:
            warehouse.delete()

        return self.api_success()

    def post_carrier(self, request, user, data):
        account = get_logistics_account(user)
        credentials = {key.replace('credentials_', ''): value for key, value in data.items() if key.startswith('credentials_')}
        form = CarrierForm({
            'account': account.id,
            'carrier_type': data['carrier_type'],
            'description': data['description'],
            'reference': data['reference'],
            'credentials': json.dumps(credentials)
        })
        errors = None
        if form.is_valid():
            carrier = form.save(commit=False)
            errors = carrier.create_source().get('errors') or []
        else:
            errors = form.errors

        return self.api_success({'errors': errors})

    def delete_carrier(self, request, user, data):
        carrier = get_logistics_account(user).carriers.filter(id=data['id']).first()
        if carrier is None:
            return self.api_error('Carrier Not Found', status=404)

        easypost = get_easypost_api(user, debug=False)
        easypost.CarrierAccount.retrieve(carrier.source_id).delete()
        carrier.delete()
        return self.api_success()

    def delete_product(self, request, user, data):
        product = user.models_user.logistics_products.filter(id=data['id']).first()
        if product is None:
            return self.api_error('Product Not Found', status=404)

        product.delete()
        return self.api_success()

    def delete_supplier(self, request, user, data):
        supplier = Supplier.objects.filter(product__user=user.models_user, id=data['id']).first()
        if supplier is None:
            return self.api_error('Product Not Found', status=404)

        supplier.delete()
        return self.api_success()

    def post_connect(self, request, user, data):
        supplier = Supplier.objects.filter(product__user=user.models_user, id=data['id']).first()
        result = {}
        if data.get('dropified_id'):
            result = supplier.connect_supplier(data['store_type'], data['store_id'], data['dropified_id'])
        elif data.get('product_id'):
            result = supplier.connect_product(data['store_type'], data['store_id'], data['product_id'])
        return self.api_success(result)

    def post_purchase_credits(self, request, user, data):
        models_user = user.models_user
        if not models_user.have_stripe_billing():
            return self.api_error("No default payment method found, add one at your Profile.", status=400)

        customer = models_user.stripe_customer.retrieve()
        credits = safe_int(data.get('credits'), 0)
        if not credits:
            return self.api_error("No credits selected", status=400)

        stripe.InvoiceItem.create(
            customer=customer.id,
            unit_amount=int(credits * 100),
            quantity=1,
            currency='usd',
            description=f"{credits} 3PL Credits",  # Must have Credits in description
        )

        invoice = stripe.Invoice.create(
            customer=customer.id,
            description='Dropified 3PL Credits',
            collection_method='charge_automatically',
            metadata=dict(
                source='3PL',
            )
        )
        response = invoice.pay()

        if not response['paid']:
            return self.api_error('Payment failed', status=400)

        try:
            balance = models_user.logistics_balance
        except AccountBalance.DoesNotExist:
            balance = AccountBalance.objects.create(user=models_user, balance=0)

        AccountCredit.objects.create(
            amount=credits,
            stripe_charge_id=invoice['id'],
            balance=balance,
        )
        AccountBalance.objects.filter(id=balance.id).update(balance=models.F('balance') + Decimal(credits))
        balance.refresh_from_db()
        return self.api_success({'balance': money_format(balance.balance)})
