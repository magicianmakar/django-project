import arrow

from django.conf import settings
from django.core.cache import cache

from shopified_core.mixins import ApiResponseMixin
from shopified_core.models_utils import get_track_model
from shopified_core.utils import safe_int

from .decorators import can_access_store
from .models import AlibabaOrder
from .utils import AlibabaUnknownError, OrderProcess, save_alibaba_products


class AlibabaApi(ApiResponseMixin):

    @can_access_store(store=True)
    def post_process_orders(self, request, user, data, store):
        if not user.can('alibaba_integration.use'):
            return self.api_error('Your current plan doesn\'t have this feature.', status=500)

        if not user.can('place_alibaba_orders.sub'):
            return self.api_error('Subuser not allowed to place orders in alibaba', status=403)

        # Check for the store auto fulfill limit
        parent_user = user.models_user
        auto_fulfill_limit = parent_user.profile.get_auto_fulfill_limit()
        limit_check_key = f'order_limit_{store.store_type}_{parent_user.id}'
        if cache.get(limit_check_key) is None and auto_fulfill_limit != -1:
            month_start = arrow.utcnow().floor('month').datetime
            order_track = get_track_model(store_type=store.store_type)
            orders_count = order_track.objects.filter(user=parent_user, created_at__gte=month_start).count()

            if not settings.DEBUG and not auto_fulfill_limit or orders_count + 1 > auto_fulfill_limit:
                return self.api_error('You have reached your plan auto fulfill limit', status=403)

            cache.set(limit_check_key, arrow.utcnow().timestamp, timeout=3600)

        parent_user = user.models_user
        alibaba_account = parent_user.alibaba.first()
        if alibaba_account is None:
            return self.api_error('Missing alibaba account, did you connected at settings?', status=403)

        place_order = not data.get('validate')
        alibaba_order_ids = None
        try:
            order_process = OrderProcess(parent_user, store, data['order_data_ids'], data.get('order_splits'),
                                         data.get('order_shippings', {}), safe_int(data.get('debug', 0)),
                                         use_cache='use_cache' in data)
            orders = order_process.get_orders_info()

            if place_order:
                orders, alibaba_order_ids = order_process.create_unpaid_orders(orders)

        except AlibabaUnknownError as e:
            return self.api_success({'error': str(e), 'orders': orders}, status=500)

        return self.api_success({'orders': orders, 'alibaba_order_ids': alibaba_order_ids or None})

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
            order = AlibabaOrder.objects.get(trade_id=data['source_id'], user=user.models_user)
        except AlibabaOrder.DoesNotExist:
            return self.api_error('Order not found', status=404)

        if order.alibaba_account is None:
            return self.api_error('Missing alibaba account, did you connected at settings?', status=403)

        details = order.reload_details()
        items = order.items.filter(order_track_id=data['track_id'])
        if len(items):
            [i.save_order_track() for i in items]
        else:
            [i.save_order_track() for i in order.items.all()]

        return self.api_success(details)

    def get_import(self, request, user, data):
        save_alibaba_products(request, {
            user.id: [int(data.get('pid'))]
        })

        return self.api_success()

    def post_pay_orders(self, request, user, data):
        if not user.can('alibaba_integration.use'):
            return self.api_error('Your current plan doesn\'t have this feature.', status=500)

        alibaba_account = user.alibaba.first()
        if not alibaba_account:
            return self.api_error('Missing connection with Alibaba.')

        result = alibaba_account.pay_orders(request.META, data['order_data_ids'])
        return self.api_success(result)

    def post_import_alibaba_product(self, request, user, data):
        for import_to in data['store_ids']:
            products = save_alibaba_products(request, {
                user.id: [int(data.get('pid'))]
            }, import_to=import_to, publish=data['publish'])
            if products.get('errored', []):
                return self.api_error(products['errored'][0])
        return self.api_success()
