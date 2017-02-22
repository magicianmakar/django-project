import re

from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_http_methods
from django.http import HttpResponse
from django.views.generic import ListView

from shopified_core import permissions
from shopified_core.utils import safeInt, safeFloat, SimplePaginator

from .models import CommerceHQStore, CommerceHQProduct
from .forms import CommerceHQStoreForm
from .decorators import no_subusers, must_be_authenticated, ajax_only


def get_product(request, post_per_page=25, sort=None, board=None, load_boards=False):
    store = request.GET.get('store')
    sort = request.GET.get('sort')

    models_user = request.user.models_user
    user = request.user
    user_stores = request.user.profile.get_chq_stores(flat=True)
    res = CommerceHQProduct.objects.select_related('store') \
                                   .filter(user=models_user)

    if request.user.is_subuser:
        res = res.filter(store__in=user_stores)
    else:
        res = res.filter(Q(store__in=user_stores) | Q(store=None))

    if store:
        if store == 'c':  # connected
            res = res.exclude(source_id=0)
        elif store == 'n':  # non-connected
            res = res.filter(source_id=0)

            in_store = safeInt(request.GET.get('in'))
            if in_store:
                in_store = get_object_or_404(CommerceHQStore, id=in_store)
                res = res.filter(store=in_store)

                permissions.user_can_view(user, in_store)
        else:
            store = get_object_or_404(CommerceHQStore, id=store)
            res = res.filter(source_id__gt=0, store=store)

            permissions.user_can_view(user, store)

    # if board:
        res = res.filter(shopifyboard=board)
        # permissions.user_can_view(user, get_object_or_404(ShopifyBoard, id=board))

    res = filter_products(res, request.GET)

    if sort:
        if re.match(r'^-?(title|price)$', sort):
            res = res.order_by(sort)

    return res


def filter_products(res, fdata):
    if fdata.get('title'):
        res = res.filter(title__icontains=fdata.get('title'))

    if fdata.get('price_min') or fdata.get('price_max'):
        min_price = safeFloat(fdata.get('price_min'), -1)
        max_price = safeFloat(fdata.get('price_max'), -1)

        if (min_price > 0 and max_price > 0):
            res = res.filter(price__gte=min_price, price__lte=max_price)

        elif (min_price > 0):
            res = res.filter(price__gte=min_price)

        elif (max_price > 0):
            res = res.filter(price__lte=max_price)

    if fdata.get('type'):
        res = res.filter(product_type__icontains=fdata.get('type'))

    if fdata.get('tag'):
        res = res.filter(tag__icontains=fdata.get('tag'))

    if fdata.get('vendor'):
        res = res.filter(default_supplier__supplier_name__icontains=fdata.get('vendor'))

    return res


@login_required
def index_view(request):
    stores = CommerceHQStore.objects.filter(user=request.user.models_user)
    can_add, total_allowed, user_count = permissions.can_add_store(request.user)
    is_stripe = request.user.profile.plan.is_stripe()
    store_count = request.user.profile.get_shopify_stores().count()
    store_count += request.user.profile.get_chq_stores().count()
    extra_stores = can_add and is_stripe and store_count >= 1
    context = {'stores': stores, 'extra_stores': extra_stores}

    return render(request, 'commercehq/index.html', context)


@ajax_only
@must_be_authenticated
@no_subusers
@csrf_protect
@require_http_methods(['POST'])
def store_create(request):
    form = CommerceHQStoreForm(request.POST)

    if form.is_valid():
        store = form.save(commit=False)
        store.user = request.user.models_user
        store.save()
        return HttpResponse(status=201)

    return render(request, 'commercehq/store_create_form.html', {'form': form})


@ajax_only
@must_be_authenticated
@no_subusers
@csrf_protect
@require_http_methods(['GET', 'POST'])
def store_update(request, store_id):
    instance = get_object_or_404(CommerceHQStore, user=request.user.models_user, pk=store_id)
    form = CommerceHQStoreForm(request.POST or None, instance=instance)

    if request.method == 'POST' and form.is_valid():
        form.save()
        return HttpResponse(status=201)

    return render(request, 'commercehq/store_update_form.html', {'form': form})


@ajax_only
@must_be_authenticated
@no_subusers
@csrf_protect
@require_http_methods(['POST'])
def store_delete(request, store_id):
    instance = get_object_or_404(CommerceHQStore, user=request.user.models_user, pk=store_id)
    instance.delete()

    return HttpResponse()


class ProductsList(ListView):
    model = CommerceHQProduct
    template_name = 'commercehq/products_grid.html'
    context_object_name = 'products'

    paginator_class = SimplePaginator
    paginate_by = 25

    def get_queryset(self):
        return get_product(self.request)

    def get_context_data(self, **kwargs):
        breadcrumbs = [{'title': 'Products', 'url': '/product'}]

        if self.request.GET.get('store', 'n') == 'n':
            breadcrumbs.append({'title': 'Non Connected', 'url': '/product?store=n'})
        elif self.request.GET.get('store', 'n') == 'c':
            breadcrumbs.append({'title': 'Connected', 'url': '/product?store=c'})

        kwargs['breadcrumbs'] = breadcrumbs

        return super(ProductsList, self).get_context_data(**kwargs)
