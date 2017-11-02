from django.contrib import messages

from django.contrib.auth.decorators import login_required
from raven.contrib.django.raven_compat.models import client as raven_client
from django.http import HttpResponseRedirect
from django.shortcuts import render
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.urlresolvers import reverse

from leadgalaxy import utils
from shopified_core.paginators import SimplePaginator


from dropwow_core.utils import (
    get_dropwow_products,
    get_dropwow_featured_products,
    get_dropwow_product,
    get_dropwow_categories,
)


@login_required
def marketplace(request):
    if not request.user.can('dropwow.use'):
        raise PermissionDenied()

    page = utils.safeInt(request.GET.get('page', 1))
    title = request.GET.get('title', '')
    category_id = utils.safeInt(request.GET.get('category_id', 0))
    min_price = utils.safeInt(request.GET.get('min_price'), '')
    max_price = utils.safeInt(request.GET.get('max_price'), '')
    brand = request.GET.get('brand')
    vendor = request.GET.get('vendor')
    order_by = request.GET.get('order_by', 'title')

    if not hasattr(request.user, 'dropwow_account'):
        messages.error(request, 'Dropwow Account not found')
        return HttpResponseRedirect('/user/profile#integration')

    try:
        featured_products = None
        if not title:
            try:
                featured_products = get_dropwow_featured_products(4).get('results', [])
            except:
                raven_client.captureException()

        categories = get_dropwow_categories().get('results', [])
        post_per_page = request.GET.get('ppp', 25)
        feed = get_dropwow_products(page, post_per_page, title, category_id, min_price, max_price, brand, vendor, order_by)
        total_items = feed.get('count', 0)
        all_products = [[] for i in range(1, total_items)]
        paginator = SimplePaginator(all_products, post_per_page)
        page = paginator.page(page)
        products = feed.get('results', [])
    except:
        raven_client.captureException()
        return HttpResponseRedirect('/')

    return render(request, 'marketplace.html', {
        'dropwow_categories': categories,
        'dropwow_products': products,
        'dropwow_featured_products': featured_products,
        'paginator': paginator,
        'current_page': page,
        'category_id': category_id,

        'page': 'marketplace',
        'breadcrumbs': [{'title': 'Marketplace', 'url': reverse('marketplace:index')}]
    })


@login_required
def marketplace_categories(request):
    if not request.user.can('marketplace.use'):
        raise PermissionDenied()

    if not hasattr(request.user, 'dropwow_account'):
        messages.error(request, 'Dropwow Account not found')
        return HttpResponseRedirect('/user/profile#integration')

    try:
        categories = get_dropwow_categories().get('results', [])

    except:
        raven_client.captureException()
        return HttpResponseRedirect('/')

    return render(request, 'marketplace_categories.html', {
        'dropwow_categories': categories,

        'page': 'marketplace',
        'breadcrumbs': [{'title': 'Marketplace', 'url': reverse('marketplace:index')}, 'All Categories']
    })


@login_required
def dropwow_product(request, dropwow_product_id):
    try:
        product = get_dropwow_product(dropwow_product_id)
        if product.get('description'):
            product['description'] = product.get('description').strip()

    except ValidationError:
        raven_client.captureException()
        return HttpResponseRedirect('/')

    return render(request, 'dropwow_product.html', {
        'product': product,
        'combinations': product['combinations'],

        'page': 'marketplace',
        'breadcrumbs': [{'title': 'Marketplace', 'url': reverse('marketplace:index')}, product['title']]
    })
