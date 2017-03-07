import re
import arrow

from raven.contrib.django.raven_compat.models import client as raven_client

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.core.urlresolvers import reverse
from django.db.models import Q
from django.http import HttpResponse, Http404
from django.shortcuts import render, get_object_or_404
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_http_methods
from django.views.generic import ListView
from django.views.generic.base import RedirectView
from django.views.generic.detail import DetailView


from shopified_core import permissions
from shopified_core.utils import (
    safeInt,
    safeFloat,
    aws_s3_context,
    clean_query_id,
    SimplePaginator
)

from .forms import CommerceHQStoreForm, CommerceHQBoardForm
from .decorators import no_subusers, must_be_authenticated, ajax_only
from .models import (
    CommerceHQStore,
    CommerceHQProduct,
    CommerceHQBoard,
    CommerceHQOrderTrack
)
from .utils import (
    CommerceHQOrdersPaginator,
    get_store_from_request,
    commercehq_products,
    chq_customer_address,
    get_tracking_orders,
    order_id_from_name
)


@ajax_only
@must_be_authenticated
@no_subusers
@csrf_protect
@require_http_methods(['POST'])
def store_create(request):
    form = CommerceHQStoreForm(request.POST)

    if form.is_valid():
        form.instance.user = request.user.models_user
        form.save()
        return HttpResponse(status=204)

    return render(request, 'commercehq/store_create_form.html', {'form': form})


@ajax_only
@must_be_authenticated
@no_subusers
@csrf_protect
@require_http_methods(['GET', 'POST'])
def store_update(request, store_id):
    store = get_object_or_404(CommerceHQStore, user=request.user.models_user, pk=store_id)
    form = CommerceHQStoreForm(request.POST or None, instance=store)

    if request.method == 'POST' and form.is_valid():
        form.save()
        return HttpResponse(status=204)

    return render(request, 'commercehq/store_update_form.html', {'form': form})


class StoresList(ListView):
    model = CommerceHQStore
    context_object_name = 'stores'
    template_name = 'commercehq/index.html'

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        if not request.user.can('commercehq.use'):
            raise permissions.PermissionDenied()

        return super(StoresList, self).dispatch(request, *args, **kwargs)

    def get_queryset(self):
        qs = super(StoresList, self).get_queryset()
        return qs.filter(user=self.request.user.models_user).filter(is_active=True)

    def is_first_visit(self):
        config = self.request.user.models_user.profile.get_config()
        first_visit = config.get('_first_visit', True)
        if first_visit:
            self.request.user.set_config('_first_visit', False)

        return first_visit

    def get_store_count(self):
        store_count = self.request.user.profile.get_shopify_stores().count()
        store_count += self.request.user.profile.get_chq_stores().count()

        return store_count

    def get_context_data(self, **kwargs):
        context = super(StoresList, self).get_context_data(**kwargs)
        can_add, total_allowed, user_count = permissions.can_add_store(self.request.user)
        is_stripe = self.request.user.profile.plan.is_stripe()
        context['extra_stores'] = can_add and is_stripe and self.get_store_count() >= 1
        context['first_visit'] = self.is_first_visit()
        context['breadcrumbs'] = ['Stores']

        return context


class BoardsList(ListView):
    model = CommerceHQBoard
    context_object_name = 'boards'
    template_name = 'commercehq/boards_list.html'

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        return super(BoardsList, self).dispatch(request, *args, **kwargs)

    def get_queryset(self):
        qs = super(BoardsList, self).get_queryset()
        return qs.filter(user=self.request.user.models_user)

    def get_context_data(self, **kwargs):
        context = super(BoardsList, self).get_context_data(**kwargs)
        context['breadcrumbs'] = ['Boards']

        return context


class BoardDetailView(DetailView):
    model = CommerceHQBoard
    context_object_name = 'board'
    template_name = 'commercehq/board.html'

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        return super(BoardDetailView, self).dispatch(request, *args, **kwargs)

    def get_queryset(self):
        qs = super(BoardDetailView, self).get_queryset()
        return qs.filter(user=self.request.user.models_user)

    def get_context_data(self, **kwargs):
        context = super(BoardDetailView, self).get_context_data(**kwargs)
        board = self.get_object()
        context['breadcrumbs'] = ['Boards', board.title]

        return context


class ProductsList(ListView):
    model = CommerceHQProduct
    template_name = 'commercehq/products_grid.html'
    context_object_name = 'products'

    paginator_class = SimplePaginator
    paginate_by = 25

    def get_queryset(self):
        return commercehq_products(self.request)

    def get_context_data(self, **kwargs):
        context = super(ProductsList, self).get_context_data(**kwargs)

        context['breadcrumbs'] = [{'title': 'Products', 'url': reverse('chq:products_list')}]

        if self.request.GET.get('store', 'n') == 'n':
            context['breadcrumbs'].append({'title': 'Non Connected', 'url': reverse('chq:products_list') + '?store=n'})
        elif self.request.GET.get('store', 'n') == 'c':
            context['breadcrumbs'].append({'title': 'Connected', 'url': reverse('chq:products_list') + '?store=c'})
        elif safeInt(self.request.GET.get('store')):
            store = CommerceHQStore.objects.get(id=self.request.GET.get('store'))
            permissions.user_can_view(self.request.user, store)

            context['store'] = store
            context['breadcrumbs'].append({'title': store.title, 'url': '{}?store={}'.format(reverse('chq:products_list'), store.id)})

        return context


class ProductDetailView(DetailView):
    model = CommerceHQProduct
    template_name = 'commercehq/product_detail.html'
    context_object_name = 'product'

    def get_context_data(self, **kwargs):
        context = super(ProductDetailView, self).get_context_data(**kwargs)

        permissions.user_can_view(self.request.user, self.object)

        if self.object.source_id:
            context['commercehq_product'] = self.object.sync()

        context['breadcrumbs'] = [
            {'title': 'Products', 'url': reverse('chq:products_list')},
            {'title': self.object.store.title, 'url': '{}?store={}'.format(reverse('chq:products_list'), self.object.store.id)},
            self.object.title
        ]

        context.update(aws_s3_context())

        return context


class OrdersList(ListView):
    model = CommerceHQProduct
    template_name = 'commercehq/orders_list.html'
    # context_object_name = 'orders'

    paginator_class = CommerceHQOrdersPaginator
    paginate_by = 20

    def get_queryset(self):
        return []

    def get_paginator(self, *args, **kwargs):
        paginator = super(OrdersList, self).get_paginator(*args, **kwargs)
        paginator.set_store(self.get_store())
        paginator.set_request(self.request)

        return paginator

    def get_context_data(self, **kwargs):
        context = super(OrdersList, self).get_context_data(**kwargs)

        context['store'] = self.get_store()

        context['breadcrumbs'] = [{
            'title': 'Orders',
            'url': reverse('chq:orders_list')
        }, {
            'title': context['store'].title,
            'url': '{}?store={}'.format(reverse('chq:orders_list'), context['store'].id)
        }]

        context['orders'] = self.get_orders(context)

        return context

    def get_store(self):
        if not hasattr(self, 'store'):
            self.store = get_store_from_request(self.request)

        return self.store

    def get_orders(self, ctx):
        models_user = self.request.user.models_user
        auto_orders = self.request.user.can('auto_order.use')

        products_cache = {}
        orders_list = {}
        orders_cache = {}

        orders_ids = []
        products_ids = []
        orders_list = {}

        orders = ctx['object_list']
        if orders is None:
            orders = []

        for order in orders:
            orders_ids.append(order['id'])
            for line in order['items']:
                products_ids.append(line.get('product_id'))

        res = CommerceHQOrderTrack.objects.filter(store=self.store, order_id__in=orders_ids).defer('data')
        for i in res:
            orders_list['{}-{}'.format(i.order_id, i.line_id)] = i

        for odx, order in enumerate(orders):
            created_at = arrow.get(order['order_date'])
            try:
                created_at = created_at.to(self.request.session['django_timezone'])
            except:
                raven_client.captureException(level='warning')

            order['date'] = created_at
            order['date_str'] = created_at.format('MM/DD/YYYY')
            order['date_tooltip'] = created_at.format('YYYY/MM/DD HH:mm:ss')
            order['order_url'] = self.store.get_admin_url('admin', 'orders', order['order_number'])
            order['store'] = self.store
            order['placed_orders'] = 0
            order['connected_lines'] = 0
            order['lines_count'] = len(order['items'])
            order['refunded_lines'] = []

            # if type(order['refunds']) is list:
            #     for refund in order['refunds']:
            #         for refund_line in refund['refund_line_items']:
            #             order['refunded_lines'].append(refund_line['line_item_id'])

            order_status = {
                0: 'Not sent to fulfilment',
                1: 'Partially sent to fulfilment',
                2: 'Partially sent to fulfilment & shipped',
                3: 'Sent to fulfilment',
                4: 'Partially shipped',
                5: 'Shipped',
            }

            paid_status = {
                0: 'Not paid',
                1: 'Paid',
                2: 'Partially refunded',
                3: 'Fully refunded',
            }

            order['fulfillment_status'] = order_status.get(order['status'])
            order['financial_status'] = paid_status.get(order['paid'])

            for fulfilment in order['fulfilments']:
                for item in fulfilment['items']:
                    orders_cache['chq_fulfilments_{}_{}_{}'.format(self.store.id, order['id'], item['id'])] = fulfilment['id']

            for ldx, line in enumerate(order['items']):
                line.update(line.get('data'))
                line.update(line.get('status'))

                variant_id = line.get('variant', {}).get('id')

                line['variant_link'] = self.store.get_admin_url('admin/products/view?id={}'.format(line['product_id']))

                if variant_id:
                    line['variant_link'] += '&variant={}'.format(variant_id)

                line['refunded'] = line['id'] in order['refunded_lines']

                line['image'] = (line.get('image') or '').replace('/uploads/', '/uploads/thumbnail_')

                line['order_track'] = orders_list.get('{}-{}'.format(order['id'], line['id']))

                if line['order_track'] or line['fulfilled'] == line['quantity'] or line['shipped'] == line['quantity']:
                    order['placed_orders'] += 1

                orders_cache['chq_quantity_{}_{}_{}'.format(self.store.id, order['id'], line['id'])] = line['quantity']

                if not line['product_id']:
                    if variant_id:
                        product = CommerceHQProduct.objects.filter(store=self.store, title=line['title'], source_id__gt=0).first()
                    else:
                        product = None
                elif line['product_id'] in products_cache:
                    product = products_cache[line['product_id']]
                else:
                    product = CommerceHQProduct.objects.filter(store=self.store, source_id=line['product_id']).first()

                supplier = None
                if product and product.have_supplier():
                    supplier = product.get_suppier_for_variant(variant_id)
                    if supplier:
                        shipping_method = product.get_shipping_for_variant(
                            supplier_id=supplier.id,
                            variant_id=variant_id,
                            country_code=order['address']['shipping']['country'])
                    else:
                        shipping_method = None

                    line['product'] = product
                    line['supplier'] = supplier
                    line['shipping_method'] = shipping_method

                    order['connected_lines'] += 1

                products_cache[line['product_id']] = product

                order['shipping_address'] = order['address']['shipping']
                if not auto_orders or not order.get('shipping_address'):
                    order['items'][ldx] = line
                    continue

                customer_address = chq_customer_address(order)

                phone = order['address']['phone']
                if not phone or models_user.get_config('order_default_phone') != 'customer':
                    phone = models_user.get_config('order_phone_number')

                if phone:
                    phone = re.sub('[^0-9/-]', '', phone)

                order['customer_address'] = customer_address

                order_data = {
                    'id': '{}_{}_{}'.format(self.store.id, order['id'], line['id']),
                    'quantity': line['quantity'],
                    'shipping_address': customer_address,
                    'order_id': order['id'],
                    'line_id': line['id'],
                    'product_id': product.id if product else None,
                    'source_id': supplier.get_source_id() if supplier else None,
                    'total': safeFloat(line['price'], 0.0),
                    'store': self.store.id,
                    'order': {
                        'phone': phone,
                        'note': models_user.get_config('order_custom_note'),
                        'epacket': bool(models_user.get_config('epacket_shipping')),
                        'auto_mark': bool(models_user.get_config('auto_ordered_mark', True)),  # Auto mark as Ordered
                    }
                }

                if product:
                    # mapped = product.get_variant_mapping(name=variant_id, for_extension=True, mapping_supplier=True)
                    # if variant_id and mapped:
                        # order_data['variant'] = mapped
                    # else:
                        # order_data['variant'] = line.get('variant', {}).get('variant', '')
                    order_data['variant'] = line.get('variant', {}).get('variant', '')

                if product and product.have_supplier():
                    orders_cache['order_{}'.format(order_data['id'])] = order_data
                    line['order_data_id'] = order_data['id']

                    line['order_data'] = order_data

                order['items'][ldx] = line

            orders[odx] = order

        cache.set_many(orders_cache, timeout=3600)

        return orders


class OrderPlaceRedirectView(RedirectView):
    permanent = False
    query_string = False

    def get_redirect_url(self, *args, **kwargs):
        try:
            assert self.request.GET['product']
            assert self.request.GET['SAPlaceOrder']

            product = self.request.GET['product']
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
            if k.startswith('SA') and k not in redirect_url:
                redirect_url = affiliate_link_set_query(redirect_url, k, self.request.GET[k])

        redirect_url = affiliate_link_set_query(redirect_url, 'SAStore', 'chq')

        # Verify if the user didn't pass order limit
        parent_user = self.request.user.models_user
        plan = parent_user.profile.plan
        if plan.auto_fulfill_limit != -1:
            month_start = [i.datetime for i in arrow.utcnow().span('month')][0]
            orders_count = parent_user.shopifyordertrack_set.filter(created_at__gte=month_start).count()

            if not plan.auto_fulfill_limit or orders_count + 1 > plan.auto_fulfill_limit:
                messages.error(self.request, "You have reached your plan auto fulfill limit")
                return '/'

        return redirect_url


class OrdersTrackList(ListView):
    model = CommerceHQOrderTrack
    paginator_class = SimplePaginator
    template_name = 'commercehq/orders_track.html'
    context_object_name = 'orders'
    paginate_by = 20

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

        orders = CommerceHQOrderTrack.objects.select_related('store') \
                                             .filter(user=self.request.user.models_user, store=store) \
                                             .defer('data')

        if query:
            order_id = order_id_from_name(store, query)

            if order_id:
                query = str(order_id)

            orders = orders.filter(Q(order_id=clean_query_id(query)) |
                                   Q(source_id=clean_query_id(query)) |
                                   Q(source_tracking__icontains=query))

        if tracking_filter == '0':
            orders = orders.filter(source_tracking='')
        elif tracking_filter == '1':
            orders = orders.exclude(source_tracking='')

        if fulfillment_filter == '1':
            orders = orders.filter(commercehq_status='fulfilled')
        elif fulfillment_filter == '0':
            orders = orders.exclude(commercehq_status='fulfilled')

        if hidden_filter == '1':
            orders = orders.filter(hidden=True)
        elif not hidden_filter or hidden_filter == '0':
            orders = orders.exclude(hidden=True)

        if completed == '1':
            orders = orders.exclude(source_status='FINISH')

        if source_reason:
            orders = orders.filter(source_status_details=source_reason)

        return orders.order_by(sorting)

    def get_context_data(self, **kwargs):
        context = super(OrdersTrackList, self).get_context_data(**kwargs)

        context['store'] = self.get_store()
        context['orders'] = get_tracking_orders(self.get_store(), context['orders'])

        context['breadcrumbs'] = [{
            'title': 'Orders',
            'url': reverse('chq:orders_list')
        }, {
            'title': 'Tracking',
            'url': reverse('chq:orders_track')
        }, {
            'title': context['store'].title,
            'url': '{}?store={}'.format(reverse('chq:orders_list'), context['store'].id)
        }]

        return context

    def get_store(self):
        if not hasattr(self, 'store'):
            self.store = get_store_from_request(self.request)

        return self.store
