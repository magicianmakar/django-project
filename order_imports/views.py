import json

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.core.urlresolvers import reverse
from django.http import JsonResponse
from django.shortcuts import render, redirect

from leadgalaxy.models import ShopifyStore
from order_imports.api import ShopifyOrderImportAPI


def index(request):
    if not request.user.can('order_imports.use'):
        raise PermissionDenied()

    stores = request.user.profile.get_active_stores()
    breadcrumbs = [
        {'url': reverse('orders'), 'title': 'Orders'},
        'Import Tracking #\'s'
    ]

    return render(request, 'order_imports/index.html', {
        'stores': stores,
        'page': 'orders',
        'breadcrumbs': breadcrumbs
    })


def upload(request, store_id):
    if not request.user.can('order_imports.use'):
        return JsonResponse({'error': 'Your current plan doesn\'t have this feature.'}, status=500)

    if request.method == 'POST':
        store = ShopifyStore.objects.get(id=store_id)
        api = ShopifyOrderImportAPI(store=store)

        data = api.parse_csv(csv_file=request.FILES.get('file'))
        return JsonResponse({'orders': data.values(), 'store_id': store_id})

    return JsonResponse({'error': 'Unsupported Request Method'}, status=501)


def approve(request):
    if not request.user.can('order_imports.use'):
        raise PermissionDenied()

    data = json.loads(request.POST.get('data', '{}'))

    for store, items in data.items():
        api = ShopifyOrderImportAPI(store=ShopifyStore.objects.get(id=store))
        api.send_tracking_number(items)

    messages.success(request, 'Imported tracking numbers for orders successfuly')
    return redirect('order_imports_index')
