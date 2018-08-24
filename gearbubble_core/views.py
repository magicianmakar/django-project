import arrow
import json

from raven.contrib.django.raven_compat.models import client as raven_client

from django.views.generic import ListView
from django.views.generic.detail import DetailView
from django.views.generic.base import RedirectView
from django.utils.decorators import method_decorator
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.urlresolvers import reverse, reverse_lazy
from django.conf import settings
from django.db.models import Q
from django.shortcuts import redirect, render
from django.core.cache import cache, caches
from django.http import Http404, JsonResponse

from shopified_core import permissions
from shopified_core.paginators import SimplePaginator
from shopified_core.shipping_helper import get_counrties_list
from shopified_core.utils import (
    safeInt,
    safeFloat,
    aws_s3_context,
    clean_query_id,
)

from .decorators import platform_permission_required, HasSubuserPermission
from .models import (
    GearBubbleStore,
    GearBubbleProduct,
    GearBubbleBoard,
    GearBubbleOrderTrack,
)
from .utils import (
    gearbubble_products,
    get_store_from_request,
    store_shipping_carriers,
    gear_customer_address,
    order_id_from_name,
    get_tracking_orders,
    get_tracking_products,
    get_api_url,
    add_details_from_product_data,
    OrderListQuery,
    OrderListPaginator,
)


def autocomplete(request, target):
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'User login required'})

    q = request.GET.get('query', '').strip()

    if not q:
        return JsonResponse({'query': q, 'suggestions': []}, safe=False)

    if target == 'types':
        types = []
        for product in request.user.models_user.gearbubbleproduct_set.only('product_type').filter(product_type__icontains=q)[:10]:
            if product.product_type not in types:
                types.append(product.product_type)

        return JsonResponse({'query': q, 'suggestions': [{'value': i, 'data': i} for i in types]}, safe=False)

    return JsonResponse({'error': 'Unknown target'})


class StoresList(ListView):
    model = GearBubbleStore
    context_object_name = 'stores'
    template_name = 'gearbubble/index.html'

    @method_decorator(login_required)
    @method_decorator(platform_permission_required)
    def dispatch(self, request, *args, **kwargs):
        return super(StoresList, self).dispatch(request, *args, **kwargs)

    def get_queryset(self):
        return self.request.user.profile.get_gear_stores()

    def get_context_data(self, **kwargs):
        context = super(StoresList, self).get_context_data(**kwargs)
        can_add, total_allowed, user_count = permissions.can_add_store(self.request.user)
        is_stripe = self.request.user.profile.plan.is_stripe()
        stores_count = self.request.user.profile.get_stores_count()
        context['extra_stores'] = can_add and is_stripe and stores_count >= 1 and total_allowed != -1
        context['user_statistics'] = cache.get('gear_user_statistics_{}'.format(self.request.user.id))
        context['breadcrumbs'] = ['Stores']

        return context


class ProductsList(ListView):
    model = GearBubbleProduct
    template_name = 'gearbubble/products_grid.html'
    context_object_name = 'products'
    paginator_class = SimplePaginator
    paginate_by = 25

    @method_decorator(login_required)
    @method_decorator(platform_permission_required)
    def dispatch(self, request, *args, **kwargs):
        return super(ProductsList, self).dispatch(request, *args, **kwargs)

    def get_queryset(self):
        return gearbubble_products(self.request)

    def get_context_data(self, **kwargs):
        context = super(ProductsList, self).get_context_data(**kwargs)

        context['breadcrumbs'] = [{'title': 'Products', 'url': reverse('gear:products_list')}]

        if self.request.GET.get('store', 'n') == 'n':
            context['breadcrumbs'].append({'title': 'Non Connected', 'url': reverse('gear:products_list') + '?store=n'})
        elif self.request.GET.get('store', 'n') == 'c':
            context['breadcrumbs'].append({'title': 'Connected', 'url': reverse('gear:products_list') + '?store=c'})
        elif safeInt(self.request.GET.get('store')):
            store = GearBubbleStore.objects.get(id=self.request.GET.get('store'))
            permissions.user_can_view(self.request.user, store)
            context['store'] = store
            context['breadcrumbs'].append({'title': store.title, 'url': '{}?store={}'.format(reverse('gear:products_list'), store.id)})

        return context


class ProductDetailView(DetailView):
    model = GearBubbleProduct
    template_name = 'gearbubble/product_detail.html'
    context_object_name = 'product'

    @method_decorator(login_required)
    @method_decorator(platform_permission_required)
    def dispatch(self, request, *args, **kwargs):
        return super(ProductDetailView, self).dispatch(request, *args, **kwargs)

    def get_object(self, *args, **kwargs):
        product = super(ProductDetailView, self).get_object(*args, **kwargs)
        permissions.user_can_view(self.request.user, product)

        return product

    def get_context_data(self, **kwargs):
        products_path = reverse('gear:products_list')
        context = super(ProductDetailView, self).get_context_data(**kwargs)
        context['gearbubble_product'] = self.object.sync() if self.object.source_id else None
        context['product_data'] = self.object.parsed
        context['default_qty'] = settings.GEARBUBBLE_DEFAULT_QTY
        context['breadcrumbs'] = [{'title': 'Products', 'url': products_path}, self.object.title]

        if self.object.store:
            store_title = self.object.store.title
            store_products_path = '{}?store={}'.format(products_path, self.object.store.id)
            context['breadcrumbs'].insert(1, {'title': store_title, 'url': store_products_path})

        context.update(aws_s3_context())

        return context


class BoardsList(ListView):
    model = GearBubbleBoard
    context_object_name = 'boards'
    template_name = 'gearbubble/boards_list.html'

    @method_decorator(login_required)
    @method_decorator(platform_permission_required)
    @method_decorator(HasSubuserPermission('view_product_boards.sub'))
    def dispatch(self, request, *args, **kwargs):
        return super(BoardsList, self).dispatch(request, *args, **kwargs)

    def get_queryset(self):
        user = self.request.user.models_user

        return super(BoardsList, self).get_queryset().filter(user=user)

    def get_context_data(self, **kwargs):
        context = super(BoardsList, self).get_context_data(**kwargs)
        context['breadcrumbs'] = ['Boards']

        return context


class BoardDetailView(DetailView):
    model = GearBubbleBoard
    context_object_name = 'board'
    template_name = 'gearbubble/board.html'

    @method_decorator(login_required)
    @method_decorator(platform_permission_required)
    @method_decorator(HasSubuserPermission('view_product_boards.sub'))
    def dispatch(self, request, *args, **kwargs):
        return super(BoardDetailView, self).dispatch(request, *args, **kwargs)

    def get_object(self, queryset=None):
        board = super(BoardDetailView, self).get_object(queryset)
        permissions.user_can_view(self.request.user, board)

        return board

    def get_queryset(self):
        user = self.request.user.models_user

        return super(BoardDetailView, self).get_queryset().filter(user=user)

    def get_context_data(self, **kwargs):
        context = super(BoardDetailView, self).get_context_data(**kwargs)
        products = gearbubble_products(self.request, store=None, board=self.object.id)
        paginator = SimplePaginator(products, 25)
        page = safeInt(self.request.GET.get('page'), 1)
        page = paginator.page(page)
        context['searchable'] = True
        context['paginator'] = paginator
        context['products'] = page
        context['current_page'] = page
        context['breadcrumbs'] = [{'title': 'Boards', 'url': reverse('gear:boards_list')}, self.object.title]

        return context


class OrdersList(ListView):
    model = None
    template_name = 'gearbubble/orders_list.html'
    context_object_name = 'orders'
    paginate_by = 20
    paginator_class = OrderListPaginator
    url = reverse_lazy('gear:orders_list')

    @method_decorator(login_required)
    @method_decorator(platform_permission_required)
    def dispatch(self, request, *args, **kwargs):
        if not request.user.can('place_orders.sub', self.get_store()):
            messages.warning(request, "You don't have access to this store's orders")
            return redirect('/gear')

        return super(OrdersList, self).dispatch(request, *args, **kwargs)

    def get_store(self):
        if not hasattr(self, 'store'):
            self.store = get_store_from_request(self.request)

        return self.store

    def get_queryset(self, *args, **kwargs):
        params = {}

        statuses = ['all', 'paid', 'expedite', 'refunded', 'canceled']
        if self.request.GET.get('status') in statuses:
            params['status'] = self.request.GET['status']

        fulfillment_statuses = ['any', 'shipped', 'unshipped']
        if self.request.GET.get('fulfillment') in fulfillment_statuses:
            params['fulfillment_status'] = self.request.GET['fulfillment']

        return OrderListQuery(self.get_store(), params)

    def get_context_data(self, **kwargs):
        context = super(OrdersList, self).get_context_data(**kwargs)
        context['store'] = store = self.get_store()
        context['orders'] = self.normalize_orders(context)
        context['shipping_carriers'] = store_shipping_carriers(store)
        context['status'] = self.request.GET.get('status', 'any')
        context['fulfillment'] = self.request.GET.get('fulfillment', 'any')

        context['breadcrumbs'] = [
            {'title': 'Orders', 'url': self.url},
            {'title': store.title, 'url': '{}?store={}'.format(self.url, store.id)},
        ]

        return context

    def get_order_date_created(self, order):
        created_at = order.get('created_at')
        if created_at:
            date_created = arrow.get(created_at)
            timezone = self.request.session.get('django_timezone')
            return date_created.to(timezone) if timezone else date_created

    def get_order_date_paid(self, order):
        order_at = order.get('order_at')
        if order_at:
            order_at = arrow.get(order_at)
            timezone = self.request.session.get('django_timezone')
            return order_at.to(timezone).datetime if timezone else order_at.datetime

    def get_order_data(self, order, item, product, supplier):
        store = self.get_store()
        models_user = self.request.user.models_user

        return {
            'id': '{}_{}_{}'.format(store.id, order['id'], item['id']),
            'quantity': item['qty'],
            'shipping_address': gear_customer_address(order),
            'order_id': order['id'],
            'line_id': item['id'],
            'product_id': product.id,
            'product_source_id': product.source_id,
            'source_id': supplier.get_source_id(),
            'total': safeFloat(item['price'], 0.0),
            'store': store.id,
            'order': {
                'note': models_user.get_config('order_custom_note'),
                'epacket': bool(models_user.get_config('epacket_shipping')),
                'auto_mark': bool(models_user.get_config('auto_ordered_mark', True)),  # Auto mark as Ordered
                'phone': {
                    'number': order.get('phone_number'),
                    'country': order.get('country'),
                },
            },
        }

    def get_order_data_variant(self, line):
        return [{'title': value} for value in line.get('variant_option', {}).values()]

    def get_products_by_source_id(self, product_ids):
        products_by_source_id = {}
        store = self.get_store()
        products = GearBubbleProduct.objects.filter(store=store, source_id__in=product_ids)

        for product in products:
            products_by_source_id[product.source_id] = product

        return products_by_source_id

    def get_product_data_by_source_id(self, product_ids):
        product_data_by_source_id = {}
        store = self.get_store()
        product_ids = [str(pk) for pk in product_ids]
        products = []
        page = 1

        while page:
            params = {'page': page, 'ids': ','.join(product_ids), 'limit': 50}
            r = store.request.get(get_api_url('private_products'), params=params)

            if r.ok:
                products += r.json()['products']
                page += 1

            if r.status_code == 404:
                break

            r.raise_for_status()

        for product in products:
            product_data_by_source_id[product['id']] = product

        return product_data_by_source_id

    def get_order_tracks_by_item(self, order_ids):
        tracks_by_item = {}
        store = self.get_store()
        tracks = GearBubbleOrderTrack.objects.filter(store=store, order_id__in=order_ids)

        for track in tracks:
            tracks_by_item['{}_{}'.format(track.order_id, track.line_id)] = track

        return tracks_by_item

    def normalize_orders(self, context):
        orders_cache = {}
        store = self.get_store()
        orders = context.get('orders', [])
        gearbubble_site = settings.GEARBUBBLE_URL.rstrip('/')
        product_ids = [order['vendor_product_id'] for order in orders]
        products_by_source_id = self.get_products_by_source_id(product_ids)
        product_data_by_source_id = self.get_product_data_by_source_id(product_ids)
        order_ids = [order['id'] for order in orders]
        order_tracks_by_item = self.get_order_tracks_by_item(order_ids)

        for order in orders:
            date_created = self.get_order_date_created(order)
            order['date_paid'] = self.get_order_date_paid(order)
            order['date'] = date_created.datetime
            order['date_str'] = date_created.format('MM/DD/YYYY')
            order['date_tooltip'] = date_created.format('YYYY/MM/DD HH:mm:ss')
            order['order_url'] = '{}/{}'.format(gearbubble_site, 'private_orders')
            order['store'] = store
            order['placed_orders'] = 0
            order['connected_lines'] = 0
            order['items'] = order.pop('line_items')
            order['lines_count'] = len(order['items'])
            product_id = order['vendor_product_id']
            product = products_by_source_id.get(product_id)
            product_data = product_data_by_source_id.get(product_id)

            for item in order.get('items', []):
                item['product'] = product
                item['product_id'] = order['vendor_product_id']
                item['quantity'] = item['qty']
                item['total'] = safeFloat(item['price'] * item['qty'])
                item = add_details_from_product_data(item, product_data)

                if product and product.has_supplier:
                    item['supplier'] = supplier = product.default_supplier
                    order_data = self.get_order_data(order, item, product, supplier)
                    order_data['variant'] = self.get_order_data_variant(item)
                    order_data_id = order_data['id']
                    orders_cache['gear_order_{}'.format(order_data_id)] = order_data
                    item['order_data_id'] = order_data_id
                    item['order_data'] = order_data

                key = '{}_{}'.format(order['id'], item['id'])
                item['order_track'] = order_tracks_by_item.get(key)

        caches['orders'].set_many(orders_cache, timeout=21600)

        return orders


class OrderPlaceRedirectView(RedirectView):
    permanent = False
    query_string = False

    @method_decorator(login_required)
    @method_decorator(platform_permission_required)
    def dispatch(self, request, *args, **kwargs):
        return super(OrderPlaceRedirectView, self).dispatch(request, *args, **kwargs)

    def get_redirect_url(self, *args, **kwargs):
        try:
            assert self.request.GET['product']

            product = self.request.GET['product']
            if safeInt(product):
                product = 'https://www.aliexpress.com/item//{}.html'.format(product)

        except:
            raven_client.captureException()
            raise Http404("Product or Order not set")

        from leadgalaxy.utils import (
            get_aliexpress_credentials,
            get_admitad_credentials,
            get_aliexpress_affiliate_url,
            get_admitad_affiliate_url,
            affiliate_link_set_query
        )

        ali_api_key, ali_tracking_id, user_ali_credentials = get_aliexpress_credentials(self.request.user.models_user)
        admitad_site_id, user_admitad_credentials = get_admitad_credentials(self.request.user.models_user)

        disable_affiliate = self.request.user.get_config('_disable_affiliate', False)

        redirect_url = False
        if not disable_affiliate:
            if user_admitad_credentials:
                service = 'admitad'
            elif user_ali_credentials:
                service = 'ali'
            else:
                service = 'admitad'

            if service == 'ali' and ali_api_key and ali_tracking_id:
                redirect_url = get_aliexpress_affiliate_url(ali_api_key, ali_tracking_id, product)
            elif service == 'admitad':
                redirect_url = get_admitad_affiliate_url(admitad_site_id, product)

        if not redirect_url:
            redirect_url = product

        for k in self.request.GET.keys():
            if k.startswith('SA') and k not in redirect_url and self.request.GET[k]:
                redirect_url = affiliate_link_set_query(redirect_url, k, self.request.GET[k])

        redirect_url = affiliate_link_set_query(redirect_url, 'SAStore', 'gear')

        # Verify if the user didn't pass order limit
        parent_user = self.request.user.models_user
        plan = parent_user.profile.plan
        if plan.auto_fulfill_limit != -1:
            month_start = [i.datetime for i in arrow.utcnow().span('month')][0]
            orders_count = parent_user.gearbubbleordertrack_set.filter(created_at__gte=month_start).count()

            if not plan.auto_fulfill_limit or orders_count + 1 > plan.auto_fulfill_limit:
                messages.error(self.request, "You have reached your plan auto fulfill limit")
                return '/'

        return redirect_url


class OrdersTrackList(ListView):
    model = GearBubbleOrderTrack
    template_name = 'gearbubble/orders_track.html'
    context_object_name = 'orders'
    paginate_by = 20

    @method_decorator(login_required)
    @method_decorator(platform_permission_required)
    def dispatch(self, request, *args, **kwargs):
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

        for k, v in order_map.items():
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
        user = self.request.user.models_user
        orders = GearBubbleOrderTrack.objects.select_related('store')
        orders = orders.filter(user=user, store=store)
        orders = orders.defer('data')

        if query:
            order_id = order_id_from_name(store, query)

            if order_id:
                query = str(order_id)

            orders = orders.filter(
                Q(order_id=clean_query_id(query)) |
                Q(source_id=clean_query_id(query)) |
                Q(source_tracking__icontains=query)
            )

        if tracking_filter == '0':
            orders = orders.filter(source_tracking='')
        elif tracking_filter == '1':
            orders = orders.exclude(source_tracking='')

        if fulfillment_filter == '1':
            orders = orders.filter(gearbubble_status='fulfilled')
        elif fulfillment_filter == '0':
            orders = orders.exclude(gearbubble_status='fulfilled')

        if hidden_filter == '1':
            orders = orders.filter(hidden=True)
        elif not hidden_filter or hidden_filter == '0':
            orders = orders.exclude(hidden=True)

        if completed == '1':
            orders = orders.exclude(source_status='completed')

        if source_reason:
            orders = orders.filter(source_status_details=source_reason)

        orders = orders.order_by(sorting)
        orders = get_tracking_orders(store, orders)
        orders = get_tracking_products(store, orders)

        return orders

    def get_context_data(self, **kwargs):
        context = super(OrdersTrackList, self).get_context_data(**kwargs)
        context['store'] = store = self.get_store()
        context['shipping_carriers'] = store_shipping_carriers(store)
        context['gearbubble_url'] = settings.GEARBUBBLE_URL
        context['breadcrumbs'] = [
            {'title': 'Orders', 'url': reverse('gear:orders_list')},
            {'title': 'Tracking', 'url': reverse('gear:orders_track')},
            {'title': store.title, 'url': '{}?store={}'.format(reverse('gear:orders_list'), store.id)},
        ]

        return context

    def get_store(self):
        if not hasattr(self, 'store'):
            self.store = get_store_from_request(self.request)

        return self.store


class VariantsEditView(DetailView):
    model = GearBubbleProduct
    template_name = 'gearbubble/variants_edit.html'
    slug_field = 'source_id'
    slug_url_kwarg = 'pid'

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        if not request.user.can('product_variant_setup.use'):
            return render(request, 'gearbubble/upgrade.html')

        return super(VariantsEditView, self).dispatch(request, *args, **kwargs)

    def get_object(self, queryset=None):
        product = super(VariantsEditView, self).get_object(queryset)
        permissions.user_can_view(self.request.user, product)

        return product

    def get_context_data(self, **kwargs):
        context = super(VariantsEditView, self).get_context_data(**kwargs)
        product_data = self.object.get_product_data()
        context['product'] = product_data
        context['store'] = self.object.store
        context['product_id'] = self.object.source_id
        context['page'] = 'product'
        url = reverse('gear:products_list')
        context['breadcrumbs'] = [{'title': 'Products', 'url': url}, 'Edit Variants']

        return context


class ProductMappingView(DetailView):
    model = GearBubbleProduct
    template_name = 'gearbubble/product_mapping.html'
    context_object_name = 'product'

    @method_decorator(login_required)
    @method_decorator(platform_permission_required)
    def dispatch(self, request, *args, **kwargs):
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

    def get_variants_map(self, gearbubble_product, product, supplier):
        variants_map = product.get_variant_mapping(supplier=supplier)
        variants_map = {key: json.loads(value) for key, value in variants_map.items()}

        for variant in gearbubble_product.get('variants', []):
            options = GearBubbleProduct.get_variant_options(variant)
            options = [{'title': option} for option in options]
            variants_map.setdefault(str(variant['id']), options)

        return variants_map

    def get_context_data(self, **kwargs):
        context = super(ProductMappingView, self).get_context_data(**kwargs)
        product = self.object
        gearbubble_product = product.sync()
        context['gearbubble_product'] = gearbubble_product
        context['product'] = product
        context['store'] = product.store
        context['product_id'] = product.id
        context['product_suppliers'] = self.get_product_suppliers(product)
        context['current_supplier'] = current_supplier = self.get_current_supplier(product)
        context['variants_map'] = self.get_variants_map(gearbubble_product, product, current_supplier)

        return context


class MappingSupplierView(DetailView):
    model = GearBubbleProduct
    template_name = 'gearbubble/mapping_supplier.html'
    context_object_name = 'product'

    @method_decorator(login_required)
    @method_decorator(platform_permission_required)
    def dispatch(self, request, *args, **kwargs):
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
        for variant in variants:
            default_supplier = {'supplier': self.object.default_supplier.id, 'shipping': {}}
            supplier = suppliers_map.get(str(variant['id']), default_supplier)
            suppliers_map[str(variant['id'])] = supplier
            variant['supplier'] = supplier['supplier']
            variant['shipping'] = supplier['shipping']

    def get_context_data(self, **kwargs):
        context = super(MappingSupplierView, self).get_context_data(**kwargs)
        product = self.object
        gearbubble_product = product.sync()
        context['gearbubble_product'] = gearbubble_product
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
            {'title': 'Products', 'url': reverse('gear:products_list')},
            {'title': product.store.title, 'url': '{}?store={}'.format(reverse('gear:products_list'), product.store.id)},
            {'title': product.title, 'url': reverse('gear:product_detail', args=[product.id])},
            'Advanced Mapping'
        ]

        self.add_supplier_info(gearbubble_product.get('variants', []), suppliers_map)

        return context
