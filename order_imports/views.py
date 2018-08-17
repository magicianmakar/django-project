import simplejson as json

from django.core.cache import cache
from django.core.exceptions import PermissionDenied
from django.urls import reverse
from django.http import JsonResponse
from django.shortcuts import render, get_object_or_404

from shopified_core.exceptions import ApiProcessException
from leadgalaxy.utils import get_store_from_request, safeInt

from .tasks import import_orders, approve_imported_orders
from .api import ShopifyOrderImportAPI


def index(request):
    if not request.user.can('order_imports.use'):
        raise PermissionDenied()

    stores = request.user.profile.get_shopify_stores()
    breadcrumbs = [
        {'url': reverse('orders'), 'title': 'Orders'},
        {'url': reverse('orders_track'), 'title': 'Tracking'},
        'Import Tracking #\'s'
    ]

    return render(request, 'order_imports/index.html', {
        'stores': stores,
        'page': 'orders_track',
        'breadcrumbs': breadcrumbs
    })


def upload(request, store_id):
    if not request.user.can('order_imports.use'):
        return JsonResponse({'error': 'Your current plan doesn\'t have this feature.'}, status=500)

    if request.method == 'POST':
        stores = request.user.profile.get_shopify_stores()
        store = get_object_or_404(stores, id=safeInt(store_id))
        api = ShopifyOrderImportAPI(store=store)

        raw_headers = {
            'order_id_position': request.GET.get('order_id_position'),
            'order_id_name': request.GET.get('order_id_name'),
            'line_item_position': request.GET.get('line_item_position'),
            'line_item_name': request.GET.get('line_item_name'),
            'tracking_number_position': request.GET.get('tracking_number_position'),
            'tracking_number_name': request.GET.get('tracking_number_name'),
            'identify_column_position': request.GET.get('identify_column_position'),
            'identify_column_name': request.GET.get('identify_column_name'),
        }

        try:
            headers = api.parse_headers(request.FILES.get('file'), raw_headers)
        except ApiProcessException as e:
            return JsonResponse({'success': False, 'error': str(e)}, status=422)
        except:
            return JsonResponse({'success': False, 'error': 'Server Error'}, status=501)

        parsed_orders = api.read_csv_file(request.FILES.get('file'), headers)
        import_orders.delay(store_id, parsed_orders, int(request.GET.get('file_index', '0')))
        return JsonResponse({'success': True, 'message': 'Reading CSV File', 'loading': 10, 'store_id': store_id})

    return JsonResponse({'success': False, 'error': 'Unsupported Request Method'}, status=501)


def approve(request):
    if not request.user.can('order_imports.use'):
        raise PermissionDenied()

    data = json.loads(request.POST.get('data', '{}'))
    pusher_store_id = int(request.POST.get('pusher_store_id'))
    approve_imported_orders.delay(request.user.id, data, pusher_store_id)

    return JsonResponse({'success': True})


def found_orders(request):
    if not request.user.can('order_imports.use'):
        raise PermissionDenied()

    store = get_store_from_request(request)
    file_index = request.GET.get('file_index', '0')

    orders = cache.get('order_import_{}_{}'.format(file_index, store.pusher_channel()))

    return JsonResponse({'orders': orders})
