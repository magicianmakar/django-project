import re
import arrow

from raven.contrib.django.raven_compat.models import client as raven_client

from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.core.urlresolvers import reverse
from django.db.models import Q
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_http_methods
from django.http import HttpResponse
from django.views.generic import ListView
from django.views.generic.detail import DetailView
from django.utils.decorators import method_decorator

from shopified_core import permissions
from shopified_core.utils import safeInt, safeFloat, aws_s3_context, SimplePaginator

from .models import CommerceHQStore, CommerceHQProduct, CommerceHQBoard
from .forms import CommerceHQStoreForm, CommerceHQBoardForm
from .utils import CommerceHQOrdersPaginator, get_store_from_request, chq_customer_address
from .decorators import no_subusers, must_be_authenticated, ajax_only


def get_product(request, post_per_page=25, sort=None, board=None, load_boards=False):
    store = request.GET.get('store')
    sort = request.GET.get('sort')

    user_stores = request.user.profile.get_chq_stores(flat=True)
    res = CommerceHQProduct.objects.select_related('store') \
                                   .filter(user=request.user.models_user)

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

                permissions.user_can_view(request.user, in_store)
        else:
            store = get_object_or_404(CommerceHQStore, id=store)
            res = res.filter(source_id__gt=0, store=store)

            permissions.user_can_view(request.user, store)

    # if board:
        # res = res.filter(shopifyboard=board)
        # permissions.user_can_view(request.user, get_object_or_404(ShopifyBoard, id=board))

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
    stores = CommerceHQStore.objects.filter(user=request.user.models_user) \
                                    .filter(is_active=True)
    can_add, total_allowed, user_count = permissions.can_add_store(request.user)
    is_stripe = request.user.profile.plan.is_stripe()
    store_count = request.user.profile.get_shopify_stores().count()
    store_count += request.user.profile.get_chq_stores().count()
    extra_stores = can_add and is_stripe and store_count >= 1

    config = request.user.models_user.profile.get_config()
    first_visit = config.get('_first_visit', True)
    if first_visit:
        request.user.set_config('_first_visit', False)

    return render(request, 'commercehq/index.html', {
        'stores': stores,
        'extra_stores': extra_stores,
        'first_visit': first_visit,
        'breadcrumbs': ['Stores']
    })


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
        return HttpResponse(status=204)

    return render(request, 'commercehq/store_update_form.html', {'form': form})


@ajax_only
@must_be_authenticated
@no_subusers
@csrf_protect
@require_http_methods(['POST'])
def store_delete(request, store_id):
    instance = get_object_or_404(CommerceHQStore, user=request.user.models_user, pk=store_id)
    instance.is_active = False
    instance.save()

    return HttpResponse()


@ajax_only
@must_be_authenticated
@csrf_protect
@require_http_methods(['POST'])
def board_create(request):
    form = CommerceHQBoardForm(request.POST)

    if form.is_valid():
        form.instance.user = request.user.models_user
        form.save()
        return HttpResponse(status=201)

    return render(request, 'commercehq/board_create_form.html', {'form': form})


@ajax_only
@must_be_authenticated
@csrf_protect
@require_http_methods(['GET', 'POST'])
def board_update(request, board_id):
    instance = get_object_or_404(CommerceHQBoard, user=request.user.models_user, pk=board_id)
    form = CommerceHQBoardForm(request.POST or None, instance=instance)

    if request.method == 'POST' and form.is_valid():
        form.save()
        return HttpResponse(status=204)

    return render(request, 'commercehq/board_update_form.html', {'form': form})


@ajax_only
@must_be_authenticated
@csrf_protect
@require_http_methods(['POST'])
def board_delete(request, board_id):
    instance = get_object_or_404(CommerceHQBoard, user=request.user.models_user, pk=board_id)
    instance.delete()

    return HttpResponse()


class BoardsList(ListView):
    model = CommerceHQBoard
    context_object_name = 'boards'
    template_name = 'commercehq/boards_list.html'

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        return super(BoardsList, self).dispatch(request, *args, **kwargs)

    def get_queryset(self):
        qs = super(BoardsList, self).get_queryset()
        return qs.filter(user=self.request.user)

    def get_context_data(self, **kwargs):
        context = super(BoardsList, self).get_context_data(**kwargs)
        context['breadcrumbs'] = ['Boards']

        return context


class ProductsList(ListView):
    model = CommerceHQProduct
    template_name = 'commercehq/products_grid.html'
    context_object_name = 'products'

    paginator_class = SimplePaginator
    paginate_by = 25

    def get_queryset(self):
        return get_product(self.request)

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
    paginate_by = 2

    def get_queryset(self):
        return []

    def get_paginator(self, *args, **kwargs):
        paginator = super(OrdersList, self).get_paginator(*args, **kwargs)
        paginator.set_store(self.get_store())

        return paginator

    def get_context_data(self, **kwargs):
        context = super(OrdersList, self).get_context_data(**kwargs)

        context['store'] = self.get_store()

        context['breadcrumbs'] = [{
            'title': 'Orders',
            'url': reverse('chq:products_list')
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

        orders = ctx['object_list']
        for odx, order in enumerate(orders):
            created_at = arrow.get(order['order_date'])
            try:
                created_at = created_at.to(self.request.session['django_timezone'])
            except:
                raven_client.captureException(level='warning')

            order['date'] = created_at
            order['date_str'] = created_at.format('MM/DD/YYYY')
            order['date_tooltip'] = created_at.format('YYYY/MM/DD HH:mm:ss')
            order['order_url'] = self.store.get_admin_url('admin/orders/%d' % order['id'])
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
                0: None,
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

            for ldx, line in enumerate(order['items']):
                line.update(line.get('data'))
                line.update(line.get('status'))

                variant_id = line.get('variant', {}).get('id')

                line['variant_link'] = self.store.get_admin_url('admin/products/view?id={}'.format(line['product_id']))

                if variant_id:
                    line['variant_link'] += '&variant={}'.format(variant_id)

                line['refunded'] = line['id'] in order['refunded_lines']

                line['image'] = (line.get('image') or '').replace('/uploads/', '/uploads/thumbnail_')

                shopify_order = orders_list.get('{}-{}'.format(order['id'], line['id']))
                line['shopify_order'] = shopify_order

                if shopify_order or line['fulfilled'] == line['quantity'] or line['shipped'] == line['quantity']:
                    order['placed_orders'] += 1

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

        return orders
