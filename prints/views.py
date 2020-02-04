import json

from django.core.exceptions import PermissionDenied
from django.http import JsonResponse, Http404, HttpResponse
from django.shortcuts import render, get_object_or_404, reverse
from django.contrib.auth.decorators import login_required

from raven.contrib.django.raven_compat.models import client as raven_client

from shopified_core.utils import aws_s3_context
from leadgalaxy.models import PriceMarkupRule

from .models import Product, CustomProduct, Order
from .utils import (
    LayerApp,
    get_store_api,
    get_tracking_details,
    import_layerapp_product,
    get_price_markup,
)


@login_required
def index(request):
    if not request.user.models_user.can('print_on_demand.use'):
        raise PermissionDenied()

    breadcrumbs = [
        {'url': '/print-on-demand/', 'title': 'Print On Demand'},
        'Products',
    ]

    products = Product.objects.active()

    return render(request, 'prints/index.html', {
        'products': products,
        'breadcrumbs': breadcrumbs,
    })


@login_required
def products(request):
    if not request.user.models_user.can('print_on_demand.use'):
        raise PermissionDenied()

    breadcrumbs = [
        {'url': '/print-on-demand/', 'title': 'Print On Demand'},
        'Saved Products',
    ]

    custom_products = CustomProduct.objects.filter(user=request.user.models_user)

    return render(request, 'prints/products.html', {
        'custom_products': custom_products,
        'breadcrumbs': breadcrumbs,
    })


@login_required
def orders(request):
    if not request.user.models_user.can('print_on_demand.use'):
        raise PermissionDenied()

    breadcrumbs = [
        {'url': '/print-on-demand/', 'title': 'Print On Demand'},
        'Placed Orders',
    ]

    orders = Order.objects.filter(user=request.user.models_user)

    order_name = request.GET.get('order')
    if order_name:
        orders = orders.filter(order_name=order_name)

    return render(request, 'prints/orders.html', {
        'orders': orders,
        'breadcrumbs': breadcrumbs,
    })


@login_required
def edit(request, product_id, custom_product_id=None):
    if not request.user.models_user.can('print_on_demand.use'):
        raise PermissionDenied()

    if custom_product_id is None:
        breadcrumbs = [
            {'url': reverse('prints:index'), 'title': 'Print On Demand'},
            {'url': reverse('prints:index'), 'title': 'Products'},
            'Add',
        ]
    else:
        breadcrumbs = [
            {'url': reverse('prints:index'), 'title': 'Print On Demand'},
            {'url': reverse('prints:products'), 'title': 'Saved Products'},
            'Edit',
        ]

    product = get_object_or_404(Product, pk=product_id)
    if product.source_type == 'layerapp':
        import_layerapp_product(product)

    custom_product = None
    if custom_product_id:
        custom_product = get_object_or_404(CustomProduct, pk=custom_product_id, product_id=product_id)

    aws = aws_s3_context()

    user_costs = product.user_costs
    user = request.user.models_user
    rules = list(PriceMarkupRule.objects.filter(user=user))
    for k, user_cost in user_costs.items():
        result = get_price_markup(user, user_cost['raw_cost'], rules)
        user_cost['price'] = result[0]
        user_cost['compare_at'] = result[1]

    return render(request, 'prints/edit.html', {
        'breadcrumbs': breadcrumbs,
        'product': product,
        'user_costs': user_costs,
        'custom_product': custom_product,
        'aws_available': aws['aws_available'],
        'aws_policy': aws['aws_policy'],
        'aws_signature': aws['aws_signature'],
    })


@login_required
def save(request):
    if not request.user.models_user.can('print_on_demand.use'):
        raise PermissionDenied()

    try:
        extra_data = json.loads(request.POST.get('extra_data') or '{}')

        assert extra_data.get('styles', {}).get('data'), 'No mockups uploaded'
        assert extra_data.get('sizes', {}).get('data'), 'Missing sizes'

    except json.JSONDecodeError:
        return JsonResponse({'error': 'Error saving custom data'}, status=500)

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

    product_id = request.POST.get('product_id')
    custom_product_id = request.POST.get('custom_product_id')

    if custom_product_id:
        custom_product = CustomProduct.objects.get(pk=custom_product_id)
    else:
        custom_product = CustomProduct(product_id=product_id, user_id=request.user.models_user.id)

    custom_product.variants = request.POST.get('variants')
    custom_product.extra_data = request.POST.get('extra_data')
    custom_product.images = request.POST.get('images')

    custom_product.title = request.POST.get('title', '')
    custom_product.description = request.POST.get('description', '')
    custom_product.product_type = request.POST.get('type', '')
    custom_product.tags = request.POST.get('tags', '')
    custom_product.price = request.POST.get('price')
    custom_product.compare_at = request.POST.get('compare_at_price')
    custom_product.notes = request.POST.get('notes', '')
    custom_product.ships_from = request.POST.get('ships_from')
    custom_product.save()

    return JsonResponse({'api_data': custom_product.to_api_data(), 'custom_product_id': custom_product.id})


def product_update(request, source_id):
    product = get_object_or_404(Product, source_id=source_id)
    if product.is_layerapp:
        api_data = json.loads(request.body.decode())
        if LayerApp().is_authorized(api_data):
            import_layerapp_product(product, api_product=api_data)
        else:
            return HttpResponse(status=403)

    return JsonResponse({'status': 'ok'})


def source(request, custom_product_id):
    if not request.is_ajax():
        return HttpResponse('Copy this url address into your product connection tab')

    custom_product = CustomProduct.objects.get(id=custom_product_id)
    if request.GET.get('variants'):
        return JsonResponse(custom_product.variants_mapping, safe=False)

    if request.GET.get('supplier'):
        return JsonResponse({
            'status': 'ok',
            'name': custom_product.supplier_name,
            'url': custom_product.supplier_url
        })

    return Http404


def tracking(request, order_id):
    order_data = json.loads(request.body.decode())
    try:
        order = Order.objects.get(pk=order_id)
        skus = [{i.order_data_id: i.get_layerapp_dict()} for i in order.line_items.all()]

        # Process order only if correct lines were sent
        for item in order_data['line_items']:
            assert item.get('sku') in skus.keys(), 'Item does not exist'

    except:
        raven_client.captureException()
        return Http404

    # TODO: check if correct quantity was shipped
    if order_data['status'] != 'shipped':
        return HttpResponse(content='Accepting only shipped status', status=304)

    order.status = order.SHIPPED
    order.tracking_company = order_data['tracking_company']
    order.tracking_number = order_data['tracking_number']

    api = get_store_api(order.store_object)
    tracking_details = get_tracking_details(order)
    for item in order.line_items.all():
        response = api.post_order_fulfill_update(request, order.user, {
            **tracking_details,
            'order': item.track.id,
        })

        if response.status_code != 200:
            raven_client.captureMessage(response.content.decode("utf-8"), level='warning')
            return response

    return response
