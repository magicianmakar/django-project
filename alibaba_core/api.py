from django.core.cache import cache

from shopified_core.mixins import ApiResponseMixin
from shopified_core.utils import safe_int

from .decorators import can_access_store
from .models import AlibabaOrder
from .utils import OrderException, OrderProcess, save_alibaba_products


class AlibabaApi(ApiResponseMixin):

    @can_access_store(store=True)
    def post_process_orders(self, request, user, data, store):
        if not user.can('alibaba_integration.use'):
            return self.api_error('Your current plan doesn\'t have this feature.', status=500)

        if not user.can('place_alibaba_orders.sub'):
            return self.api_error('Subuser not allowed to place orders in alibaba', status=403)

        parent_user = user.models_user
        alibaba_account = parent_user.alibaba.first()
        if alibaba_account is None:
            return self.api_error('Missing alibaba account, did you connected at settings?', status=403)

        place_order = not data.get('validate')
        try:
            order_process = OrderProcess(parent_user, store, data['order_data_ids'], data.get('order_splits'),
                                         data.get('order_shippings', {}), safe_int(data.get('debug', 0)),
                                         use_cache='use_cache' in data)
            orders = order_process.get_orders_info()

            if place_order:
                orders = order_process.create_unpaid_orders(orders)

        except OrderException as e:
            return self.api_error(str(e), status=500)

        return self.api_success({'orders': orders})

    def get_product_data(self, request, user, data):
        if not user.can('alibaba_integration.use'):
            return self.api_error('Your current plan doesn\'t have this feature.', status=500)

        alibaba_account = user.alibaba.first()
        if alibaba_account is None:
            return self.api_error('Missing alibaba account, did you connected at settings?', status=403)

        product = alibaba_account.get_product(data['product_id'])

        return self.api_success(product)

    def get_product_variants(self, request, user, data):
        if not user.can('alibaba_integration.use'):
            return self.api_error('Your current plan doesn\'t have this feature.', status=500)

        alibaba_account = user.alibaba.first()
        if alibaba_account is None:
            return self.api_error('Missing alibaba account, did you connected at settings?', status=403)

        cache_key = f"alibaba_product_variant_{user.id}_{data['product_id']}"
        variant_data = cache.get(cache_key)
        if variant_data is not None:
            return self.api_success(variant_data)

        product = alibaba_account.get_product(data['product_id'])
        variant_data = {
            'variant_data': product['variants_map'],
        }

        cache.set(cache_key, variant_data, timeout=300)

        return self.api_success(variant_data)

    @can_access_store
    def post_sync_order(self, request, user, data):
        if not user.can('alibaba_integration.use'):
            return self.api_error('Your current plan doesn\'t have this feature.', status=500)

        try:
            order = AlibabaOrder.objects.filter(trade_id=data['source_id'], user=user.models_user)
        except AlibabaOrder.DoesNotExist:
            return self.api_error('Order not found', status=404)

        if order.alibaba_account is None:
            return self.api_error('Missing alibaba account, did you connected at settings?', status=403)

        # TODO: Check how bundles work here
        details = order.reload_details()
        return self.api_success(details)

    def post_import(self, request, user, data):
        alibaba_account = user.alibaba.first()
        if not alibaba_account:
            return self.api_error('Missing connection with Alibaba.')

        save_alibaba_products(request, {
            alibaba_account.alibaba_user_id: [int(data.get('pid'))]
        })

        return self.api_success()
