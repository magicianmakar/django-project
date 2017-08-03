import json

import arrow

from django.views.generic import ListView
from django.views.generic.detail import DetailView
from django.utils.decorators import method_decorator
from django.contrib.auth.decorators import login_required
from django.core.urlresolvers import reverse, reverse_lazy
from django.shortcuts import get_object_or_404, render

from shopified_core import permissions
from shopified_core.paginators import SimplePaginator
from shopified_core.shipping_helper import get_counrties_list
from shopified_core.utils import (
    aws_s3_context,
    safeInt,
)

from .models import WooStore, WooProduct
from .utils import (
    woocommerce_products,
    store_shipping_carriers,
    get_store_from_request,
    WooListPaginator,
    WooListQuery,
)


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
        products = reverse('woo:products_list')

        if self.object.source_id:
            context['woocommerce_product'] = self.object.sync()

        context['product_data'] = self.object.parsed
        context['breadcrumbs'] = [{'title': 'Products', 'url': products}, self.object.title]

        if self.object.store:
            store_title = self.object.store.title
            store_products = '{}?store={}'.format(products, self.object.store.id)
            context['breadcrumbs'].insert(1, {'title': store_title, 'url': store_products})

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
        pk = self.request.GET.get('supplier') or product.default_supplier.id
        return product.get_suppliers().get(pk=pk)

    def get_variants_map(self, woocommerce_product, product, supplier):
        variants_map = product.get_variant_mapping(supplier=supplier)
        variants_map = {key: json.loads(value) for key, value in variants_map.items()}
        for variant in woocommerce_product.get('variants', []):
            attributes = variant.get('attributes', [])
            options = [{'title': option['option']} for option in attributes]
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


class MappingSupplierView(DetailView):
    model = WooProduct
    template_name = 'woocommerce/mapping_supplier.html'
    context_object_name = 'product'

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        if not request.user.can('woocommerce.use'):
            raise permissions.PermissionDenied()

        return super(MappingSupplierView, self).dispatch(request, *args, **kwargs)

    def get_object(self, queryset=None):
        product = super(MappingSupplierView, self).get_object(queryset)
        permissions.user_can_view(self.request.user, product)

        return product

    def get_product_suppliers(self, product):
        suppliers = {}
        for supplier in product.get_suppliers():
            pk, name, url = supplier.id, supplier.get_name(), supplier.product_url
            suppliers[pk] = {'id': pk, 'name': name, 'url': url}

        return suppliers

    def add_supplier_info(self, variants, suppliers_map):
        for index, variant in enumerate(variants):
            default_supplier = {'supplier': self.object.default_supplier.id, 'shipping': {}}
            supplier = suppliers_map.get(str(variant['id']), default_supplier)
            suppliers_map[str(variant['id'])] = supplier
            variants[index]['supplier'] = supplier['supplier']
            variants[index]['shipping'] = supplier['shipping']

    def get_context_data(self, **kwargs):
        context = super(MappingSupplierView, self).get_context_data(**kwargs)
        product = self.object
        woocommerce_product = product.sync()
        context['woocommerce_product'] = woocommerce_product
        context['product'] = product
        context['store'] = product.store
        context['product_id'] = product.id
        context['countries'] = get_counrties_list()
        context['product_suppliers'] = self.get_product_suppliers(product)
        context['suppliers_map'] = suppliers_map = product.get_suppliers_mapping()
        context['shipping_map'] = product.get_shipping_mapping()
        context['variants_map'] = product.get_all_variants_mapping()
        context['mapping_config'] = product.get_mapping_config()
        context['breadcrumbs'] = [
            {'title': 'Products', 'url': reverse('woo:products_list')},
            {'title': product.store.title, 'url': '{}?store={}'.format(reverse('woo:products_list'), product.store.id)},
            {'title': product.title, 'url': reverse('woo:product_detail', args=[product.id])},
            'Advanced Mapping'
        ]

        self.add_supplier_info(woocommerce_product.get('variants', []), suppliers_map)

        return context


class VariantsEditView(DetailView):
    model = WooProduct
    template_name = 'woocommerce/variants_edit.html'
    slug_field = 'source_id'
    slug_url_kwarg = 'pid'

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        if not request.user.can('product_variant_setup.use'):
            return render(request, 'woocommerce/upgrade.html')

        return super(VariantsEditView, self).dispatch(request, *args, **kwargs)

    def get_object(self, queryset=None):
        product = super(VariantsEditView, self).get_object(queryset)
        permissions.user_can_view(self.request.user, product)

        return product

    def get_store(self):
        store = get_object_or_404(WooStore, pk=self.kwargs['store_id'])
        permissions.user_can_view(self.request.user, store)

        return store

    def get_context_data(self, **kwargs):
        context = super(VariantsEditView, self).get_context_data(**kwargs)
        context['product'] = self.object.retrieve()
        context['store'] = self.object.store
        context['product_id'] = self.object.source_id
        context['page'] = 'product'

        context['breadcrumbs'] = [
            {'title': 'Products', 'url': reverse('woo:products_list')},
            'Edit Variants',
        ]

        return context


class OrdersList(ListView):
    model = None
    template_name = 'woocommerce/orders_list.html'
    context_object_name = 'orders'
    paginator_class = WooListPaginator
    paginate_by = 20
    products = {}
    url = reverse_lazy('woo:orders_list')

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        if not request.user.can('woocommerce.use'):
            raise permissions.PermissionDenied()

        return super(OrdersList, self).dispatch(request, *args, **kwargs)

    def get_store(self):
        if not hasattr(self, 'store'):
            self.store = get_store_from_request(self.request)

        return self.store

    def get_filters(self):
        filters = {}
        params = self.request.GET

        if params.get('sort') in ['order_date', '!order_date']:
            filters['orderby'] = 'date'
            if params.get('sort') == 'order_date':
                filters['order'] = 'asc'
            if params.get('sort') == '!order_date':
                filters['order'] = 'desc'

        if params.get('status') and not params.get('status') == 'any':
            filters['status'] = params.get('status')

        if params.get('query'):
            filters['include'] = params.get('query')

        return filters

    def get_queryset(self):
        store, filters = self.get_store(), self.get_filters()

        return WooListQuery(store, 'orders', filters)

    def get_product_data(self, product_id):
        if product_id not in self.products:
            self.add_product_data_to_products(product_id)

        return self.products.get(product_id)

    def get_item_fulfillment_status(self, item):
        for meta in item.get('meta_data', []):
            if meta['key'] == 'Fulfillment Status':
                return meta['value']

    def get_context_data(self, **kwargs):
        context = super(OrdersList, self).get_context_data(**kwargs)
        context['store'] = store = self.get_store()
        context['status'] = self.request.GET.get('status', 'any')
        context['shipping_carriers'] = store_shipping_carriers(store)

        context['breadcrumbs'] = [
            {'title': 'Orders', 'url': self.url},
            {'title': store.title, 'url': '{}?store={}'.format(self.url, store.id)},
        ]

        self.normalize_orders(context)

        return context

    def add_product_data_to_products(self, product_id):
        r = self.get_store().wcapi.get('products/{}'.format(product_id))
        if r.status_code == 200:
            self.products.setdefault(product_id, r.json())

    def normalize_orders(self, context):
        store = self.get_store()
        admin_url = store.get_admin_url()
        timezone = self.request.session.get('django_timezone')

        for order in context.get('orders', []):
            date_created = arrow.get(order['date_created'])
            if timezone:
                date_created = date_created.to(timezone)
                if order['date_paid']:
                    order['date_paid'] = order['date_paid'].to(timezone)

            order['date'] = date_created
            order['date_str'] = date_created.format('MM/DD/YYYY')
            order['date_tooltip'] = date_created.format('YYYY/MM/DD HH:mm:ss')
            order['order_url'] = admin_url + '/post.php?post={}&action=edit'.format(order['id'])
            order['store'] = store
            order['placed_orders'] = 0
            order['connected_lines'] = 0
            order['items'] = order.pop('line_items')
            order['lines_count'] = len(order['items'])

            for item in order.get('items'):
                product_id = item['product_id']
                product = self.get_product_data(product_id)
                if product:
                    item['product'] = WooProduct.objects.filter(source_id=product_id).first()
                    item['image'] = next(iter(product['images']), {}).get('src')

                item['fulfillment_status'] = self.get_item_fulfillment_status(item)
                if item['fulfillment_status'] == 'Fulfilled':
                    order['placed_orders'] += 1

            if order['placed_orders'] == order['lines_count']:
                order['fulfillment_status'] = 'Fulfilled'
            elif order['placed_orders'] and order['placed_orders'] < order['lines_count']:
                order['fulfillment_status'] = 'Partially Fulfilled'
            else:
                order['fulfillment_status'] = None
