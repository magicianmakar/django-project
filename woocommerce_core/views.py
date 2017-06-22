import json

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


class ProductMappingView(DetailView):
    model = WooProduct
    template_name = 'woocommerce/product_mapping.html'
    context_object_name = 'product'

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        if not request.user.can('woocommerce.use'):
            raise permissions.PermissionDenied()

        return super(ProductMappingView, self).dispatch(request, *args, **kwargs)

    def get_product_suppliers(self, product):
        suppliers = {}
        for supplier in product.get_suppliers():
            pk, name, url = supplier.id, supplier.get_name(), supplier.product_url
            suppliers[pk] = {'id': pk, 'name': name, 'url': url}

        return suppliers

    def get_current_supplier(self, product):
        pk = self.request.GET.get('supplier') or getattr(product.default_supplier, 'pk', None)
        supplier = product.get_suppliers().get(pk=pk)

        return supplier

    def get_variants_map(self, woocommerce_product, product, supplier):
        variants_map = product.get_variant_mapping(supplier=supplier)
        variants_map = {key: json.loads(value) for key, value in variants_map.items()}
        for variant in woocommerce_product.get('variants', []):
            options = []
            for option in variant.get('attributes', []):
                options.append({'title': option['option']})
                variant.setdefault('variant', []).append(option['option'])
            variants_map.setdefault(str(variant['id']), options)

        return variants_map

    def get_context_data(self, **kwargs):
        context = super(ProductMappingView, self).get_context_data(**kwargs)
        product = self.object
        woocommerce_product = product.sync()
        context['woocommerce_product'] = woocommerce_product
        context['product'] = product
        context['store'] = product.store
        context['product_id'] = product.id
        context['product_suppliers'] = self.get_product_suppliers(product)
        context['current_supplier'] = current_supplier = self.get_current_supplier(product)
        context['variants_map'] = self.get_variants_map(woocommerce_product, product, current_supplier)

        return context
