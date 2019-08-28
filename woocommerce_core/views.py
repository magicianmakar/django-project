import json
import re

import arrow
import jwt
import requests

from django.conf import settings
from django.contrib import messages
from django.db.models import Q
from django.views.generic import View, ListView
from django.views.generic.detail import DetailView
from django.views.generic.base import RedirectView
from django.utils.decorators import method_decorator
from django.contrib.auth.decorators import login_required
from django.urls import reverse, reverse_lazy
from django.core.cache import cache, caches
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, render, redirect
from django.contrib.auth import get_user_model

from shopified_core import permissions
from shopified_core.paginators import SimplePaginator
from shopified_core.shipping_helper import get_counrties_list
from shopified_core.utils import (
    ALIEXPRESS_REJECTED_STATUS,
    aws_s3_context,
    safe_int,
    clean_query_id,
    safe_float,
    http_excption_status_code,
    order_data_cache,
)
from shopified_core.tasks import keen_order_event

from .models import WooStore, WooProduct, WooSupplier, WooOrderTrack, WooBoard
from .utils import (
    woocommerce_products,
    store_shipping_carriers,
    get_store_from_request,
    WooListPaginator,
    WooListQuery,
    order_id_from_name,
    get_tracking_orders,
    get_tracking_products,
    get_order_line_fulfillment_status,
    woo_customer_address,
    get_product_data,
)


class CallbackEndpoint(View):
    def dispatch(self, request, *args, **kwargs):
        self.data = json.loads(request.body)

        return super(CallbackEndpoint, self).dispatch(request, *args, **kwargs)

    def get_user(self):
        User = get_user_model()
        user = get_object_or_404(User, pk=self.data['user_id'])

        return user

    def get_store(self):
        store = get_object_or_404(WooStore, store_hash=self.kwargs['store_hash'])

        return store

    def has_credentials(self, store):
        return store.api_key and store.api_password

    def set_credentials(self, store):
        store.api_key = self.data['consumer_key']
        store.api_password = self.data['consumer_secret']
        store.save()

        return store

    def post(self, request, *args, **kwargs):
        user, store = self.get_user(), self.get_store()
        permissions.user_can_edit(user, store)
        store = self.set_credentials(store) if not self.has_credentials(store) else store

        return HttpResponse('ok')


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
        context['selected_menu'] = 'products:all'

        if self.request.GET.get('store', 'n') == 'n':
            context['breadcrumbs'].append({'title': 'Non Connected', 'url': reverse('woo:products_list') + '?store=n'})
        elif self.request.GET.get('store', 'n') == 'c':
            context['breadcrumbs'].append({'title': 'Connected', 'url': reverse('woo:products_list') + '?store=c'})
        elif safe_int(self.request.GET.get('store')):
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
            try:
                context['woocommerce_product'] = self.object.sync()
            except (requests.exceptions.HTTPError, requests.exceptions.ConnectionError) as e:
                messages.warning(self.request, f'Product details was not synced with your store (HTTP Error: {http_excption_status_code(e)})')

        context['product_data'] = self.object.parsed
        context['breadcrumbs'] = [{'title': 'Products', 'url': products}, self.object.title]
        context['selected_menu'] = 'products:all'

        if self.object.store:
            store_title = self.object.store.title
            store_products = '{}?store={}'.format(products, self.object.store.id)
            context['breadcrumbs'].insert(1, {'title': store_title, 'url': store_products})

        context.update(aws_s3_context())

        context['token'] = jwt.encode({
            'id': self.request.user.id,
            'exp': arrow.utcnow().replace(hours=6).timestamp
        }, settings.API_SECRECT_KEY, algorithm='HS256')

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
        variants_map = {key: json.loads(value) for key, value in list(variants_map.items())}
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
        context['selected_menu'] = 'products:all'

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
        context['selected_menu'] = 'products:all'

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
        kwarg = {
            'source_id': self.kwargs['pid'],
            'store': self.get_store(),
        }

        try:
            product = WooProduct.objects.get(**kwarg)
        except WooProduct.MultipleObjectsReturned:
            product = WooProduct.objects.filter(**kwarg).first()

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
        context['selected_menu'] = '3'

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

        if not self.get_store():
            messages.warning(request, 'Please add at least one store before using the Orders page.')
            return redirect('woo:index')

        if not request.user.can('place_orders.sub', self.get_store()):
            messages.warning(request, "You don't have access to this store orders")
            return redirect('woo:index')

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
        return WooListQuery(self.get_store(), 'orders', self.get_filters())

    def get_context_data(self, **kwargs):
        api_error = None

        context = {}

        try:
            context = super(OrdersList, self).get_context_data(**kwargs)
        except (requests.exceptions.HTTPError, requests.exceptions.ConnectionError) as e:
            api_error = f'HTTP Error: {http_excption_status_code(e)}'
        except:
            api_error = 'Store API Error'

        context['store'] = store = self.get_store()
        context['status'] = self.request.GET.get('status', 'any')
        context['shipping_carriers'] = store_shipping_carriers(store)

        context['breadcrumbs'] = [
            {'title': 'Orders', 'url': self.url},
            {'title': store.title, 'url': '{}?store={}'.format(self.url, store.id)}]
        context['selected_menu'] = 'orders:all'

        try:
            if not api_error:
                self.normalize_orders(context)
        except (requests.exceptions.HTTPError, requests.exceptions.ConnectionError) as e:
            api_error = f'HTTP Error: {http_excption_status_code(e)}'
        except:
            api_error = 'Store API Error'

        if api_error:
            messages.error(self.request, f'Error while trying to show your Store Orders: {api_error}')

        context['api_error'] = api_error

        return context

    def get_product_supplier(self, product, variant_id=None):
        if product.has_supplier():
            return product.get_supplier_for_variant(variant_id)

    def get_order_date_created(self, order):
        date_created = arrow.get(order['date_created'])
        timezone = self.request.session.get('django_timezone')

        return date_created if not timezone else date_created.to(timezone)

    def get_order_date_paid(self, order):
        if order.get('date_paid'):
            paid_date = arrow.get(order['date_paid'])
            timezone = self.request.session.get('django_timezone')
            if timezone:
                paid_date = paid_date.to(timezone)

            return paid_date.datetime

    def get_item_shipping_method(self, product, item, variant_id, country_code):
        if item.get('supplier'):
            return product.get_shipping_for_variant(supplier_id=item['supplier'].id,
                                                    variant_id=variant_id,
                                                    country_code=country_code)

    def get_order_data(self, order, item, product, supplier):
        store = self.get_store()
        models_user = self.request.user.models_user
        fix_aliexpress_address = models_user.get_config('fix_aliexpress_address', True)
        fix_aliexpress_city = models_user.get_config('fix_aliexpress_city', True)
        german_umlauts = models_user.get_config('_use_german_umlauts', False)

        country = order['shipping']['country'] or order['billing']['country']

        _order, shipping_address = woo_customer_address(
            order=order,
            aliexpress_fix=fix_aliexpress_address and supplier and supplier.is_aliexpress,
            fix_aliexpress_city=fix_aliexpress_city,
            german_umlauts=german_umlauts)

        return {
            'id': '{}_{}_{}'.format(store.id, order['id'], item['id']),
            'quantity': item['quantity'],
            'shipping_address': shipping_address,
            'order_id': order['id'],
            'line_id': item['id'],
            'product_id': product.id,
            'product_source_id': product.source_id,
            'source_id': supplier.get_source_id(),
            'total': safe_float(item['price'], 0.0),
            'store': store.id,
            'order': {
                'phone': {
                    'number': order['billing'].get('phone'),
                    'country': country,
                },
                'note': models_user.get_config('order_custom_note'),
                'epacket': bool(models_user.get_config('epacket_shipping')),
                'auto_mark': bool(models_user.get_config('auto_ordered_mark', True)),  # Auto mark as Ordered
            },
        }

    def get_order_data_variant(self, product, line):
        mapped = product.get_variant_mapping(name=line['variation_id'],
                                             for_extension=True,
                                             mapping_supplier=True)
        if mapped:
            return mapped

        data = self.product_data.get(product.source_id)
        if not data:
            return []

        options = []
        for attribute in data['attributes']:
            options += attribute['options']

        metas = line.get('meta_data', [])
        variant = [{'title': meta['value']} for meta in metas if meta['value'] in options]

        return variant

    def update_placed_orders(self, order, item):
        item['fulfillment_status'] = get_order_line_fulfillment_status(item)

        if item['fulfillment_status'] == 'Fulfilled':
            order['placed_orders'] += 1

        if order['placed_orders'] == order['lines_count']:
            order['fulfillment_status'] = 'Fulfilled'
        elif order['placed_orders'] > 0 and order['placed_orders'] < order['lines_count']:
            order['fulfillment_status'] = 'Partially Fulfilled'
        else:
            order['fulfillment_status'] = None

    def get_product_ids(self, orders):
        product_ids = set()
        for order in orders:
            for item in order.get('line_items', []):
                product_ids.add(item['product_id'])

        return list(product_ids)

    def get_product_by_source_id(self, product_ids):
        product_by_source_id = {}
        store = self.get_store()
        for product in WooProduct.objects.filter(store=store, source_id__in=product_ids):
            product_by_source_id[product.source_id] = product

        return product_by_source_id

    def get_product_data(self, product_ids):
        if not hasattr(self, 'product_data'):
            store = self.get_store()
            self.product_data = get_product_data(store, product_ids)

        return self.product_data

    def get_order_ids(self, orders):
        return [order['id'] for order in orders]

    def get_order_track_by_item(self, order_ids):
        track_by_item = {}
        store = self.get_store()
        for track in WooOrderTrack.objects.filter(store=store, order_id__in=order_ids):
            key = '{}_{}_{}'.format(track.order_id, track.line_id, track.product_id)
            track_by_item[key] = track

        return track_by_item

    def normalize_orders(self, context):
        orders_cache = {}
        store = self.get_store()
        admin_url = store.get_admin_url()
        orders = context.get('orders', [])
        product_ids = self.get_product_ids(orders)
        product_by_source_id = self.get_product_by_source_id(product_ids)
        product_data = self.get_product_data(product_ids)
        order_ids = self.get_order_ids(orders)
        order_track_by_item = self.get_order_track_by_item(order_ids)

        for order in orders:
            country_code = order['shipping']['country'] or order['billing']['country']
            date_created = self.get_order_date_created(order)
            order['date_paid'] = self.get_order_date_paid(order)
            order['date'] = date_created.datetime
            order['date_str'] = date_created.format('MM/DD/YYYY')
            order['date_tooltip'] = date_created.format('YYYY/MM/DD HH:mm:ss')
            order['order_url'] = '{}/post.php?post={}&action=edit'.format(admin_url, order['id'])
            order['store'] = store
            order['placed_orders'] = 0
            order['connected_lines'] = 0
            order['tracked_lines'] = 0
            order['items'] = order.pop('line_items')
            order['lines_count'] = len(order['items'])
            order['has_shipping_address'] = any(order['shipping'].values())

            for item in order.get('items'):
                self.update_placed_orders(order, item)
                product_id = item['product_id']
                product = product_by_source_id.get(product_id)
                data = product_data.get(product_id)
                item['product'] = product
                item['image'] = next(iter(data['images']), {}).get('src') if data else None
                variant_id = item.get('variation_id')

                if product and product.has_supplier():
                    supplier = self.get_product_supplier(product, variant_id)
                    order_data = self.get_order_data(order, item, product, supplier)
                    order_data['variant'] = self.get_order_data_variant(product, item)
                    order_data_id = order_data['id']
                    orders_cache['woo_order_{}'.format(order_data_id)] = order_data
                    attributes = [variant['title'] for variant in order_data['variant']]
                    item['attributes'] = ', '.join(attributes)
                    item['order_data_id'] = order_data_id
                    item['order_data'] = order_data
                    item['supplier'] = supplier
                    item['supplier_type'] = supplier.supplier_type()
                    item['shipping_method'] = self.get_item_shipping_method(
                        product, item, variant_id, country_code)

                key = '{}_{}_{}'.format(order['id'], item['id'], item['product_id'])
                item['order_track'] = order_track_by_item.get(key)
                if item['order_track']:
                    order['tracked_lines'] += 1

            if order['tracked_lines'] != 0 and \
                    order['tracked_lines'] < order['lines_count'] and \
                    order['placed_orders'] < order['lines_count']:
                order['partially_ordered'] = True

        caches['orders'].set_many(orders_cache, timeout=21600)


class OrdersTrackList(ListView):
    model = WooOrderTrack
    paginator_class = SimplePaginator
    template_name = 'woocommerce/orders_track.html'
    context_object_name = 'orders'
    paginate_by = 20

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        if not request.user.can('woocommerce.use'):
            raise permissions.PermissionDenied()

        if not self.get_store():
            messages.warning(request, 'Please add at least one store before using the Tracking page.')
            return redirect('woo:index')

        return super(OrdersTrackList, self).dispatch(request, *args, **kwargs)

    def get_queryset(self):
        if not self.request.user.can('orders.use'):
            return render(self.request, 'upgrade.html')

        order_map = {
            'order': 'order_id',
            'source': 'source_id',
            'status': 'source_status',
            'tracking': 'source_tracking',
            'add': 'created_at',
            'reason': 'source_status_details',
            'update': 'status_updated_at',
        }

        for k, v in list(order_map.items()):
            order_map['-' + k] = '-' + v

        sorting = self.request.GET.get('sort', '-update')
        sorting = order_map.get(sorting, 'status_updated_at')

        query = self.request.GET.get('query')
        tracking_filter = self.request.GET.get('tracking')
        fulfillment_filter = self.request.GET.get('fulfillment')
        hidden_filter = self.request.GET.get('hidden')
        completed = self.request.GET.get('completed')
        source_reason = self.request.GET.get('reason')

        store = self.get_store()

        orders = WooOrderTrack.objects.select_related('store') \
                                      .filter(user=self.request.user.models_user, store=store) \
                                      .defer('data')
        if query:
            order_id = order_id_from_name(store, query)

            if order_id:
                query = str(order_id)

            orders = orders.filter(Q(order_id=clean_query_id(query))
                                   | Q(source_id=clean_query_id(query))
                                   | Q(source_tracking__icontains=query))

        if tracking_filter == '0':
            orders = orders.filter(source_tracking='')
        elif tracking_filter == '1':
            orders = orders.exclude(source_tracking='')

        if fulfillment_filter == '1':
            orders = orders.filter(woocommerce_status='fulfilled')
        elif fulfillment_filter == '0':
            orders = orders.exclude(woocommerce_status='fulfilled')

        if hidden_filter == '1':
            orders = orders.filter(hidden=True)
        elif not hidden_filter or hidden_filter == '0':
            orders = orders.exclude(hidden=True)

        if completed == '1':
            orders = orders.exclude(source_status='completed')

        if source_reason:
            orders = orders.filter(source_status_details=source_reason)

        return orders.order_by(sorting)

    def get_context_data(self, **kwargs):
        context = super(OrdersTrackList, self).get_context_data(**kwargs)
        error = None

        try:
            context['store'] = self.get_store()
            context['orders'] = get_tracking_orders(self.get_store(), context['orders'], self.paginate_by)
            context['orders'] = get_tracking_products(self.get_store(), context['orders'], self.paginate_by)
            context['shipping_carriers'] = store_shipping_carriers(self.get_store())

        except (requests.exceptions.HTTPError, requests.exceptions.ConnectionError) as e:
            error = f'HTTP Error: {http_excption_status_code(e)}'
        except:
            error = 'Store API Error'

        if error:
            messages.error(self.request, f'Error while trying to show your Store Orders: {error}')

        context['api_error'] = error

        context['breadcrumbs'] = [{
            'title': 'Orders',
            'url': reverse('woo:orders_list')
        }, {
            'title': 'Tracking',
            'url': reverse('woo:orders_track')
        }, {
            'title': context['store'].title,
            'url': '{}?store={}'.format(reverse('woo:orders_list'), context['store'].id)
        }]
        context['selected_menu'] = 'orders:tracking'

        context['rejected_status'] = ALIEXPRESS_REJECTED_STATUS

        return context

    def get_store(self):
        if not hasattr(self, 'store'):
            self.store = get_store_from_request(self.request)

        return self.store


class BoardsList(ListView):
    model = WooBoard
    context_object_name = 'boards'
    template_name = 'woocommerce/boards_list.html'

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        if not request.user.can('view_product_boards.sub'):
            raise permissions.PermissionDenied()

        return super(BoardsList, self).dispatch(request, *args, **kwargs)

    def get_queryset(self):
        qs = super(BoardsList, self).get_queryset()
        return qs.filter(user=self.request.user.models_user)

    def get_context_data(self, **kwargs):
        context = super(BoardsList, self).get_context_data(**kwargs)
        context['breadcrumbs'] = ['Boards']
        context['selected_menu'] = 'products:boards'

        return context


class BoardDetailView(DetailView):
    model = WooBoard
    context_object_name = 'board'
    template_name = 'woocommerce/board.html'

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        if not request.user.can('view_product_boards.sub'):
            raise permissions.PermissionDenied()

        return super(BoardDetailView, self).dispatch(request, *args, **kwargs)

    def get_queryset(self):
        qs = super(BoardDetailView, self).get_queryset()
        return qs.filter(user=self.request.user.models_user)

    def get_context_data(self, **kwargs):
        context = super(BoardDetailView, self).get_context_data(**kwargs)
        permissions.user_can_view(self.request.user, self.object)

        products = woocommerce_products(self.request, store=None, board=self.object.id)
        paginator = SimplePaginator(products, 25)
        page = safe_int(self.request.GET.get('page'), 1)
        page = paginator.page(page)

        context['searchable'] = True
        context['paginator'] = paginator
        context['products'] = page
        context['current_page'] = page
        context['breadcrumbs'] = [{'title': 'Boards', 'url': reverse('woo:boards_list')}, self.object.title]
        context['selected_menu'] = 'products:boards'

        return context


class OrderPlaceRedirectView(RedirectView):
    permanent = False
    query_string = False

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        if not request.user.can('woocommerce.use'):
            raise permissions.PermissionDenied()

        return super(OrderPlaceRedirectView, self).dispatch(request, *args, **kwargs)

    def get_redirect_url(self, *args, **kwargs):
        product = None
        supplier = None

        disable_affiliate = self.request.user.get_config('_disable_affiliate', False)

        if self.request.GET.get('nff'):
            disable_affiliate = True

        if self.request.GET.get('supplier'):
            supplier = WooSupplier.objects.get(id=self.request.GET['supplier'])
            permissions.user_can_view(self.request.user, supplier.product)

            product = supplier.short_product_url()

        elif self.request.GET.get('product'):
            product = self.request.GET['product']

            if safe_int(product):
                product = 'https://www.aliexpress.com/item//{}.html'.format(product)

        if not product:
            return Http404("Product or Order not set")

        from leadgalaxy.utils import (
            get_aliexpress_credentials,
            get_admitad_credentials,
            get_aliexpress_affiliate_url,
            get_admitad_affiliate_url,
            get_ebay_affiliate_url,
            affiliate_link_set_query
        )

        ali_api_key, ali_tracking_id, user_ali_credentials = get_aliexpress_credentials(self.request.user.models_user)
        admitad_site_id, user_admitad_credentials = get_admitad_credentials(self.request.user.models_user)

        redirect_url = False
        if not disable_affiliate:
            if supplier and supplier.is_ebay:
                if not self.request.user.models_user.can('ebay_auto_fulfill.use'):
                    messages.error(self.request, "eBay 1-Click fulfillment is not available on your current plan. "
                                                 "Please upgrade to Premier Plan to use this feature")

                    return '/'

                redirect_url = get_ebay_affiliate_url(product)
            else:
                if user_admitad_credentials:
                    service = 'admitad'
                elif user_ali_credentials:
                    service = 'ali'
                else:
                    service = settings.DEFAULT_ALIEXPRESS_AFFILIATE

                if service == 'ali' and ali_api_key and ali_tracking_id:
                    redirect_url = get_aliexpress_affiliate_url(ali_api_key, ali_tracking_id, product)

                elif service == 'admitad':
                    redirect_url = get_admitad_affiliate_url(admitad_site_id, product)

        if not redirect_url:
            redirect_url = product

        for k in list(self.request.GET.keys()):
            if k.startswith('SA') and k not in redirect_url and self.request.GET[k]:
                redirect_url = affiliate_link_set_query(redirect_url, k, self.request.GET[k])

        redirect_url = affiliate_link_set_query(redirect_url, 'SAStore', 'woo')

        # Verify if the user didn't pass order limit
        parent_user = self.request.user.models_user
        plan = parent_user.profile.plan
        limit_check_key = 'order_limit_woo_{}'.format(parent_user.id)
        if cache.get(limit_check_key) is None and plan.auto_fulfill_limit != -1:
            month_start = [i.datetime for i in arrow.utcnow().span('month')][0]
            orders_count = parent_user.wooordertrack_set.filter(created_at__gte=month_start).count()

            if not settings.DEBUG and not plan.auto_fulfill_limit or orders_count + 1 > plan.auto_fulfill_limit:
                messages.error(self.request, "You have reached your plan auto fulfill limit")
                return '/'

            cache.set(limit_check_key, arrow.utcnow().timestamp, timeout=3600)

        # Save Auto fulfill event
        event_data = {}
        order_data = None
        order_key = self.request.GET.get('SAPlaceOrder')
        if order_key:
            event_key = 'keen_event_{}'.format(self.request.GET['SAPlaceOrder'])

            if not order_key.startswith('order_'):
                order_key = 'order_{}'.format(order_key)

            order_data = order_data_cache(f'woo_{order_key}')
            prefix, store, order, line = order_key.split('_')

        if order_data:
            order_data['url'] = redirect_url
            caches['orders'].set(order_key, order_data, timeout=caches['orders'].ttl(order_key))

        if order_data and settings.KEEN_PROJECT_ID and not cache.get(event_key):
            try:
                store = WooStore.objects.get(id=store)
                permissions.user_can_view(self.request.user, store)
            except WooStore.DoesNotExist:
                raise Http404('Store not found')

            for k in list(self.request.GET.keys()):
                if k == 'SAPlaceOrder':
                    event_data['data_id'] = self.request.GET[k]

                elif k == 'product':
                    event_data['product'] = self.request.GET[k]

                    if not safe_int(event_data['product']):  # Check if we are using product link or just the ID
                        event_data['product'] = re.findall('[/_]([0-9]+).html', event_data['product'])
                        if event_data['product']:
                            event_data['product'] = event_data['product'][0]

                elif k.startswith('SA'):
                    event_data[k[2:].lower()] = self.request.GET[k]

            affiliate = 'ShopifiedApp'
            if user_admitad_credentials:
                affiliate = 'UserAdmitad'
            elif user_ali_credentials:
                affiliate = 'UserAliexpress'

            if supplier and supplier.is_ebay:
                event_data['supplier_type'] = 'ebay'

            event_data.update({
                'user': store.user.username,
                'user_id': store.user_id,
                'store': store.title,
                'store_id': store.id,
                'store_type': 'WooCommerce',
                'plan': plan.title,
                'plan_id': plan.id,
                'affiliate': affiliate,
                'sub_user': self.request.user.is_subuser,
                'total': order_data['total'],
                'quantity': order_data['quantity'],
                'cart': 'SACart' in self.request.GET
            })

            if not settings.DEBUG:
                keen_order_event.delay("auto_fulfill", event_data)

            cache.set(event_key, True, timeout=3600)

        return redirect_url
