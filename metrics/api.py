import hashlib

from django.core.cache import cache
from django.http import JsonResponse
from django.utils.crypto import get_random_string
from django.views.generic import View

import requests

from shopified_core.utils import hash_text, get_client_ip, safe_float, using_store_db
from shopified_core.mixins import ApiResponseMixin
from shopified_core.tasks import keen_send_event
from metrics.statuspage import record_aliexpress_single_order, record_aliexpress_multi_order
from data_store.models import DataStore


class MetricsApi(ApiResponseMixin, View):

    def post_add(self, request, user, data):
        val = safe_float(data.get('value'))
        if val:
            if data.get('supplier') == 'aliexpress':
                if data.get('type') == 'single-order' and val < 200.0:
                    record_aliexpress_single_order(val)

                elif data.get('type') == 'multi-order' and val < 250.0:
                    record_aliexpress_multi_order(val)

            user_ip = get_client_ip(request)
            cache_key = f'ip_country.{hash_text(user_ip)}'
            user_country = cache.get(cache_key)
            if user_country is None:
                user_country = requests.get(f'https://ipinfo.io/{user_ip}').json().get('country')
                cache.set(cache_key, user_country, timeout=9600)

            keen_send_event.delay('auto_fulfill_timing', {
                'supplier_type': data.get('supplier'),
                'order_type': data.get('type'),
                'productVersion': data.get('productVersion'),
                'checkoutVersion': data.get('checkoutVersion'),
                'user_country': user_country,
                'user_id': user.id,
                'user_name': user.username,
                'plan_name': user.profile.plan.title,
                'extension_version': request.META.get('HTTP_X_EXTENSION_VERSION'),
                'took': val,
            })

        return JsonResponse({'status': 'ok'})

    def post_page(self, request, user, data):
        data_key = f'{get_random_string()}'.encode()
        data_key = f'page:{hashlib.md5(data_key).hexdigest()}'[:32]
        using_store_db(DataStore).create(key=data_key, data=request.POST['page'])

        return self.api_success({
            'id': data_key
        })
