from django.http import JsonResponse
from django.views.generic import View

from shopified_core.utils import safe_float
from shopified_core.mixins import ApiResponseMixin
from metrics.statuspage import record_aliexpress_single_order, record_aliexpress_multi_order


class MetricsApi(ApiResponseMixin, View):

    def post_add(self, request, user, data):
        if data.get('supplier') == 'aliexpress':
            if data.get('type') == 'single-order':
                record_aliexpress_single_order(safe_float(data['value']))

            elif data.get('type') == 'multi-order':
                record_aliexpress_multi_order(safe_float(data['value']))

        return JsonResponse({'status': 'ok'})
