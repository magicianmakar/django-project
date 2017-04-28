from django.views.generic import ListView
from django.views.generic.detail import DetailView
from django.utils.decorators import method_decorator
from django.contrib.auth.decorators import login_required
from django.core.urlresolvers import reverse

from shopified_core import permissions
from shopified_core.paginators import SimplePaginator
from shopified_core.utils import (
    aws_s3_context,
    safeInt,
)

from .models import WooStore, WooProduct
from .utils import woocommerce_products


class StoresList(ListView):
    model = WooStore
    context_object_name = 'stores'
    template_name = 'woocommerce/index.html'

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        if not request.user.can('woocommerce.use'):
            raise permissions.PermissionDenied()

        return super(StoresList, self).dispatch(request, *args, **kwargs)

    def get_queryset(self):
        qs = super(StoresList, self).get_queryset()
        return qs.filter(user=self.request.user.models_user).filter(is_active=True)

    def get_context_data(self, **kwargs):
        context = super(StoresList, self).get_context_data(**kwargs)
        can_add, total_allowed, user_count = permissions.can_add_store(self.request.user)
        is_stripe = self.request.user.profile.plan.is_stripe()
        stores_count = self.request.user.profile.get_stores_count()
        context['extra_stores'] = can_add and is_stripe and stores_count >= 1 and total_allowed != -1
        context['breadcrumbs'] = ['Stores']

        return context


class ProductsList(ListView):
    model = WooProduct
    template_name = 'woocommerce/products_grid.html'
    context_object_name = 'products'

    paginator_class = SimplePaginator
    paginate_by = 25

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        if not request.user.can('woocommerce.use'):
            raise permissions.PermissionDenied()

        return super(ProductsList, self).dispatch(request, *args, **kwargs)

    def get_queryset(self):
        return woocommerce_products(self.request)

    def get_context_data(self, **kwargs):
        context = super(ProductsList, self).get_context_data(**kwargs)

        context['breadcrumbs'] = [{'title': 'Products', 'url': reverse('woo:products_list')}]

        if self.request.GET.get('store', 'n') == 'n':
            context['breadcrumbs'].append({'title': 'Non Connected', 'url': reverse('woo:products_list') + '?store=n'})
        elif self.request.GET.get('store', 'n') == 'c':
            context['breadcrumbs'].append({'title': 'Connected', 'url': reverse('woo:products_list') + '?store=c'})
        elif safeInt(self.request.GET.get('store')):
            store = WooStore.objects.get(id=self.request.GET.get('store'))
            permissions.user_can_view(self.request.user, store)

            context['store'] = store
            context['breadcrumbs'].append({'title': store.title, 'url': '{}?store={}'.format(reverse('woo:products_list'), store.id)})

        return context


class ProductDetailView(DetailView):
    model = WooProduct
    template_name = 'woocommerce/product_detail.html'
    context_object_name = 'product'

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        if not request.user.can('woocommerce.use'):
            raise permissions.PermissionDenied()

        return super(ProductDetailView, self).dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super(ProductDetailView, self).get_context_data(**kwargs)
        permissions.user_can_view(self.request.user, self.object)

        if self.object.source_id:
            context['woocommerce_product'] = self.object.sync()

        context['product_data'] = self.object.parsed
        context['breadcrumbs'] = [
            {'title': 'Products', 'url': reverse('woo:products_list')},
            {'title': self.object.store.title, 'url': '{}?store={}'.format(reverse('woo:products_list'), self.object.store.id)},
            self.object.title
        ]

        context.update(aws_s3_context())

        return context
