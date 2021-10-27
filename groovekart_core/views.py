import re
import arrow
import simplejson as json
import requests

from lib.exceptions import capture_exception

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.cache import cache, caches
from django.urls import reverse, reverse_lazy
from django.db.models import Q
from django.http import Http404, HttpResponseRedirect, JsonResponse
from django.shortcuts import render, get_object_or_404
from django.utils.decorators import method_decorator
from django.utils import timezone
from django.views.generic import ListView
from django.views.generic.base import RedirectView
from django.views.generic.detail import DetailView
from django.core.cache.utils import make_template_fragment_key

from profits.mixins import ProfitDashboardMixin

from supplements.lib.shipstation import get_address as get_shipstation_address
from supplements.models import PLSOrder
from supplements.tasks import update_shipstation_address
from shopified_core import permissions
from shopified_core.decorators import PlatformPermissionRequired, HasSubuserPermission
from shopified_core.mocks import (
    get_mocked_bundle_variants,
    get_mocked_supplier_variants,
    get_mocked_alert_changes,
)
from shopified_core.paginators import SimplePaginator
from shopified_core.shipping_helper import get_counrties_list
from shopified_core.utils import (
    app_link,
    aws_s3_context,
    jwt_encode,
    safe_int,
    safe_float,
    clean_query_id,
    url_join,
    http_excption_status_code,
    order_data_cache,
    format_queueable_orders,
)
from shopified_core.tasks import keen_order_event
from product_alerts.models import ProductChange
from product_alerts.utils import variant_index_from_supplier_sku
from leadgalaxy.utils import (
    get_aliexpress_credentials,
    get_admitad_credentials,
    get_aliexpress_affiliate_url,
    get_admitad_affiliate_url,
    get_ebay_affiliate_url,
    affiliate_link_set_query,
    set_url_query
)

from .models import (
    GrooveKartStore,
    GrooveKartProduct,
    GrooveKartBoard,
    GrooveKartSupplier,
    GrooveKartOrderTrack,
)
from .utils import (
    OrderListPaginator,
    OrderListQuery,
    groovekart_products,
    get_store_from_request,
    store_shipping_carriers,
    gkart_customer_address,
    get_tracking_orders,
    order_id_from_name,
    get_gkart_products,
    get_orders_page_default_date_range,
    fix_gkart_image,
    get_store_categories,
)


@login_required
def product_alerts(request):
    store = get_store_from_request(request)
    if not store:
        messages.warning(request, 'Please add at least one store before using the Alerts page.')
        return HttpResponseRedirect('/gkart/')

    if not request.user.can('price_changes.use'):
        return render(request, 'groovekart/product_alerts.html', {
            'upsell': True,
            'product_changes': get_mocked_alert_changes(),
            'page': 'product_alerts',
            'store': store,
            'breadcrumbs': [{'title': 'Products', 'url': '/gkart/products'}, 'Alerts'],
            'selected_menu': 'products:alerts',
        })

    show_hidden = bool(request.GET.get('hidden'))

    product = request.GET.get('product')
    if product:
        product = get_object_or_404(GrooveKartProduct, id=product)
        permissions.user_can_view(request.user, product)

    page = safe_int(request.GET.get('page'), 1)
    post_per_page = safe_int(request.user.get_config('_gkart_list_alert_limit'), None)
    if not post_per_page:
        post_per_page = settings.ITEMS_PER_PAGE

    changes = ProductChange.objects.select_related('gkart_product') \
                                   .select_related('gkart_product__default_supplier') \
                                   .filter(user=request.user.models_user,
                                           gkart_product__store=store)

    if request.user.is_subuser:
        store_ids = request.user.profile.subuser_gkart_permissions.filter(
            codename='view_alerts'
        ).values_list(
            'store_id', flat=True
        )
        changes = changes.filter(gkart_product__store_id__in=store_ids)

    if product:
        changes = changes.filter(gkart_product=product)
    else:
        changes = changes.filter(hidden=show_hidden)

    category = request.GET.get('category')
    if category:
        changes = changes.filter(categories__icontains=category)
    product_type = request.GET.get('product_type', '')
    if product_type:
        changes = changes.filter(gkart_product__product_type__icontains=product_type)

    changes = changes.order_by('-updated_at')

    paginator = SimplePaginator(changes, post_per_page)
    page = min(max(1, page), paginator.num_pages)
    page = paginator.page(page)
    changes = page.object_list

    products = []
    product_variants = {}
    for i in changes:
        gkart_id = i.product.get_gkart_id()
        if gkart_id and str(gkart_id) not in products:
            products.append(str(gkart_id))
    try:
        if len(products):
            products = get_gkart_products(store=store, product_ids=products)
            if isinstance(products, dict):
                for i, p in products.items():
                    if isinstance(p, dict) and p.get('id'):
                        product_variants[str(p['id'])] = p
            else:
                for p in products:
                    if isinstance(p, dict) and p.get('id'):
                        product_variants[str(p['id'])] = p
    except:
        capture_exception()

    product_changes = []
    for i in changes:
        change = {'qelem': i}
        change['id'] = i.id
        change['data'] = i.get_data()
        change['changes'] = i.get_changes_map(category)
        change['product'] = i.product
        change['gkart_link'] = i.product.groovekart_url
        change['original_link'] = i.product.get_original_info().get('url')
        p = product_variants.get(str(i.product.get_gkart_id()), {})
        variants = p.get('variants', [])
        for c in change['changes']['variants']['quantity']:
            if len(variants) > 0:
                index = variant_index_from_supplier_sku(i.product, c['sku'], variants)
                if index is not None:
                    c['gkart_value'] = "Unmanaged"
                else:
                    c['gkart_value'] = "Not Found"
            else:
                c['gkart_value'] = "Unmanaged"
        for c in change['changes']['variants']['price']:
            if len(variants) > 0:
                index = variant_index_from_supplier_sku(i.product, c['sku'], variants)
                if index is not None:
                    c['gkart_value'] = variants[index]['price']
                else:
                    c['gkart_value_label'] = "Not Found"
            elif p and 'price' in p:
                c['gkart_value'] = p['price']

        product_changes.append(change)

    # Allow sending notification for new changes
    cache.delete('product_change_%d' % request.user.models_user.id)

    # Delete sidebar alert info cache
    cache.delete(make_template_fragment_key('alert_info', [request.user.id]))

    return render(request, 'groovekart/product_alerts.html', {
        'product_changes': product_changes,
        'show_hidden': show_hidden,
        'product': product,
        'paginator': paginator,
        'current_page': page,
        'page': 'product_alerts',
        'store': store,
        'category': category,
        'product_type': product_type,
        'breadcrumbs': [{'title': 'Products', 'url': '/product'}, 'Alerts']
    })


@method_decorator(login_required, name='dispatch')
@method_decorator(PlatformPermissionRequired('groovekart'), name='dispatch')
class ProductsList(ListView):
    model = GrooveKartProduct
    template_name = 'groovekart/products_grid.html'
    context_object_name = 'products'
    paginator_class = SimplePaginator
    paginate_by = 25

    def get_queryset(self):
        return groovekart_products(self.request)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['breadcrumbs'] = [{'title': 'Products', 'url': reverse('gkart:products_list')}]

        if self.request.GET.get('store', 'n') == 'n':
            context['breadcrumbs'].append({'title': 'Non Connected', 'url': reverse('gkart:products_list') + '?store=n'})
        elif self.request.GET.get('store', 'n') == 'c':
            context['breadcrumbs'].append({'title': 'Connected', 'url': reverse('gkart:products_list') + '?store=c'})
        elif safe_int(self.request.GET.get('store')):
            store = GrooveKartStore.objects.get(id=self.request.GET.get('store'))
            permissions.user_can_view(self.request.user, store)
            context['store'] = store
            context['breadcrumbs'].append({'title': store.title, 'url': '{}?store={}'.format(reverse('gkart:products_list'), store.id)})

        return context


@method_decorator(login_required, name='dispatch')
@method_decorator(PlatformPermissionRequired('groovekart'), name='dispatch')
class ProductDetailView(DetailView):
    model = GrooveKartProduct
    template_name = 'groovekart/product_detail.html'
    context_object_name = 'product'

    def get_object(self, *args, **kwargs):
        product = super().get_object(*args, **kwargs)
        permissions.user_can_view(self.request.user, product)

        return product

    def get_context_data(self, **kwargs):
        products_path = reverse('gkart:products_list')
        context = super().get_context_data(**kwargs)
        context['groovekart_product'] = self.object.sync() if self.object.source_id else None
        context['product_data'] = self.object.parsed
        context['breadcrumbs'] = [{'title': 'Products', 'url': products_path}, self.object.title]

        if self.object.store:
            store_title = self.object.store.title
            store_products_path = '{}?store={}'.format(products_path, self.object.store.id)
            context['categories'] = get_store_categories(self.object.store)
            context['breadcrumbs'].insert(1, {'title': store_title, 'url': store_products_path})

        context.update(aws_s3_context())

        last_check = None
        try:
            if self.object.monitor_id > 0:
                cache_key = 'gkart_product_last_check_{}'.format(self.object.id)
                last_check = cache.get(cache_key)

                if last_check is None:
                    response = requests.get(
                        url=url_join(settings.PRICE_MONITOR_HOSTNAME, '/api/products/', self.object.monitor_id),
                        auth=(settings.PRICE_MONITOR_USERNAME, settings.PRICE_MONITOR_PASSWORD),
                        timeout=10,
                    )

                    last_check = arrow.get(response.json()['updated_at'])
                    cache.set(cache_key, last_check, timeout=3600)
        except:
            pass
        context['last_check'] = last_check

        try:
            context['alert_config'] = json.loads(self.object.config)
        except:
            context['alert_config'] = {}

        context['token'] = jwt_encode({'id': self.request.user.id})

        context['upsell_alerts'] = not self.request.user.can('price_changes.use')
        context['config'] = self.request.user.get_config()

        return context


@method_decorator(login_required, name='dispatch')
@method_decorator(PlatformPermissionRequired('groovekart'), name='dispatch')
@method_decorator(HasSubuserPermission('view_product_boards.sub'), name='dispatch')
class BoardsList(ListView):
    model = GrooveKartBoard
    context_object_name = 'boards'
    template_name = 'groovekart/boards_list.html'

    def get_queryset(self):
        return super().get_queryset().filter(user=self.request.user.models_user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['breadcrumbs'] = ['Boards']

        return context


@method_decorator(login_required, name='dispatch')
@method_decorator(PlatformPermissionRequired('groovekart'), name='dispatch')
@method_decorator(HasSubuserPermission('view_product_boards.sub'), name='dispatch')
class BoardDetailView(DetailView):
    model = GrooveKartBoard
    context_object_name = 'board'
    template_name = 'groovekart/board.html'

    def get_object(self, queryset=None):
        board = super().get_object(queryset)
        permissions.user_can_view(self.request.user, board)

        return board

    def get_queryset(self):
        return super().get_queryset().filter(user=self.request.user.models_user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        products = groovekart_products(self.request, store=None, board=self.object.id)
        paginator = SimplePaginator(products, 25)
        page = safe_int(self.request.GET.get('page'), 1)
        page = paginator.page(page)
        context['searchable'] = True
        context['paginator'] = paginator
        context['products'] = page
        context['current_page'] = page
        context['breadcrumbs'] = [{'title': 'Boards', 'url': reverse('gkart:boards_list')}, self.object.title]

        return context


@method_decorator(login_required, name='dispatch')
@method_decorator(PlatformPermissionRequired('groovekart'), name='dispatch')
class OrdersList(ListView):
    model = None
    template_name = 'groovekart/orders_list.html'
    context_object_name = 'orders'
    paginate_by = 20
    paginator_class = OrderListPaginator
    url = reverse_lazy('gkart:orders_list')

    def dispatch(self, request, *args, **kwargs):
        if not request.user.can('orders.use'):
            return render(request, 'upgrade.html')

        store = self.get_store()
        if not store:
            messages.warning(request, 'Please add at least one store before using the Orders page.')
            return HttpResponseRedirect('/gkart/')

        if not request.user.can('place_orders.sub', store):
            messages.warning(request, "You don't have access to this store orders")
            return HttpResponseRedirect('/gkart/')

        bulk_queue = bool(request.GET.get('bulk_queue'))
        if bulk_queue and not request.user.can('bulk_order.use'):
            return JsonResponse({'error': "Your plan doesn't have Bulk Ordering feature."}, status=402)

        return super(ListView, self).dispatch(request, *args, **kwargs)

    def render_to_response(self, context, **response_kwargs):
        bulk_queue = bool(self.request.GET.get('bulk_queue'))
        if bulk_queue:
            return format_queueable_orders(self.request, context['orders'], context['page_obj'], store_type='gkart')

        return super().render_to_response(context, **response_kwargs)

    def get_store(self):
        if not hasattr(self, 'store'):
            self.store = get_store_from_request(self.request)

        return self.store

    def get_default_date_range(self):
        return '{}-{}'.format(*get_orders_page_default_date_range(timezone))

    def get_queryset(self, *args, **kwargs):
        params = {}
        params['order_by'] = self.request.GET.get('sort', 'date_add')
        order_way = self.request.GET.get('desc', 'true')
        params['order_way'] = 'DESC' if order_way == 'true' else 'ASC'

        if self.request.GET.get('status'):
            params['order_status'] = self.request.GET.get('status')

        if self.request.GET.get('query_order'):
            params['ids'] = self.request.GET.get('query_order')

        if self.request.GET.get('reference'):
            params['reference'] = self.request.GET.get('reference')

        product_ids = self.request.GET.getlist('product_ids')
        if product_ids:
            params['product_id'] = ','.join(product_ids)

        default_date_range = self.get_default_date_range()
        created_at_daterange = self.request.GET.get('created_at_daterange', default_date_range)
        created_at_start, created_at_end = None, None
        if created_at_daterange and not self.request.GET.get('query_order'):
            try:
                daterange_list = created_at_daterange.split('-')

                tz = timezone.localtime(timezone.now()).strftime(' %z')

                created_at_start = arrow.get(daterange_list[0] + tz, r'MM/DD/YYYY Z')

                if len(daterange_list) > 1 and daterange_list[1]:
                    created_at_end = arrow.get(daterange_list[1] + tz, r'MM/DD/YYYY Z')
                    created_at_end = created_at_end.span('day')[1]

            except:
                pass

        # TODO: Using only one date doesn't work
        if created_at_start and created_at_end:
            params['created_at_min'] = created_at_start.format('YYYY-MM-DD')
            params['created_at_max'] = created_at_end.format('YYYY-MM-DD')

        if self.request.GET.get('country_code'):
            params['country_code'] = self.request.GET.get('country_code')

        return OrderListQuery(self.get_store(), params)

    def get_context_data(self, **kwargs):
        api_error = None
        context = {}

        store = self.get_store()

        try:
            context = super(OrdersList, self).get_context_data(**kwargs)

            context['store'] = store
            context['orders'] = self.normalize_orders(context)
            context['shipping_carriers'] = store_shipping_carriers(store)

        except (requests.exceptions.HTTPError, requests.exceptions.ConnectionError) as e:
            api_error = f'HTTP Error: {http_excption_status_code(e)}'
        except:
            api_error = 'Store API Error'
            capture_exception()

        context['status'] = self.request.GET.get('status', 'any')
        context['fulfillment'] = self.request.GET.get('fulfillment', 'any')
        context['countries'] = get_counrties_list()

        product_ids = self.request.GET.getlist('product_ids')
        if len(product_ids):
            context['products'] = GrooveKartProduct.objects.filter(pk__in=product_ids)

        default_date_range = self.get_default_date_range()
        context['created_at_daterange'] = self.request.GET.get('created_at_daterange', default_date_range)

        context['breadcrumbs'] = [
            {'title': 'Orders', 'url': self.url},
            {'title': store.title, 'url': '{}?store={}'.format(self.url, store.id)},
        ]

        if api_error:
            messages.error(self.request, f'Error while trying to show your Store Orders: {api_error}')

        context['api_error'] = api_error

        return context

    def get_order_date_created(self, order):
        created_at = order.get('created_at')
        if created_at:
            try:
                date_created = arrow.get(f"{created_at} -0400", 'YYYY-MM-DD HH:mm:ss ZZ')
                dj_timezone = self.request.session.get('django_timezone')
                return date_created.to(dj_timezone) if dj_timezone else date_created
            except arrow.parser.ParserError:
                return arrow.get(created_at)

    def get_order_date_paid(self, order):
        # TODO
        return None
        order_at = order.get('order_at')
        if order_at:
            order_at = arrow.get(order_at)
            timezone = self.request.session.get('django_timezone')
            return order_at.to(timezone).datetime if timezone else order_at.datetime

    def get_item_shipping_method(self, product, item, variant_id, country_code):
        if item.get('supplier'):
            return product.get_shipping_for_variant(supplier_id=item['supplier'].id,
                                                    variant_id=variant_id,
                                                    country_code=country_code)

    def get_order_data(self, order, item, product, supplier):
        store = self.get_store()
        models_user = self.request.user.models_user
        aliexpress_fix = models_user.get_config('aliexpress_fix_city', True)

        return {
            'id': '{}_{}_{}'.format(store.id, order['id'], item['id']),
            'order_name': order['id'],
            'title': item['title'],
            'quantity': safe_int(item['quantity']),
            'shipping_address': gkart_customer_address(
                order,
                aliexpress_fix=aliexpress_fix,
                shipstation_fix=supplier.is_pls if supplier else False
            ),
            'order_id': safe_int(order['id']),
            'line_id': safe_int(item['id']),
            'product_id': product.id,
            'product_source_id': product.source_id,
            'source_id': supplier.get_source_id() if supplier else None,
            'supplier_id': supplier.get_store_id() if supplier else None,
            'supplier_type': supplier.supplier_type() if supplier else None,
            'total': safe_float(item['price'], 0.0),
            'store': store.id,
            'order': {
                'note': models_user.get_config('order_custom_note'),
                'epacket': bool(models_user.get_config('epacket_shipping')),
                'aliexpress_shipping_method': models_user.get_config('aliexpress_shipping_method'),
                'auto_mark': bool(models_user.get_config('auto_ordered_mark', True)),  # Auto mark as Ordered
                'phone': {
                    'number': order.get('shipping_address', {}).get('phone'),
                    'country': order.get('shipping_address', {}).get('country'),
                },
            },
        }

    def get_order_data_variant(self, line):
        return [{'title': option.get('value')} for option in line.get('variants', {}).get('options', [])]

    def get_products_by_source_id(self, product_ids):
        product_by_source_id = {}
        store = self.get_store()
        for product in GrooveKartProduct.objects.filter(store=store, source_id__in=product_ids):
            product_by_source_id[product.source_id] = product

        return product_by_source_id

    def get_order_tracks_by_item(self, order_ids):
        tracks_by_item = {}
        store = self.get_store()
        tracks = GrooveKartOrderTrack.objects.filter(store=store, order_id__in=order_ids)

        for track in tracks:
            tracks_by_item['{}_{}'.format(track.order_id, track.line_id)] = track

        return tracks_by_item

    def get_unfulfilled_supplement_items(self, order_ids):
        store = self.get_store()
        unfulfilled_supplement_items = {}
        for o in PLSOrder.objects.prefetch_related('order_items',
                                                   'order_items__label',
                                                   'order_items__label__user_supplement',
                                                   ).filter(is_fulfilled=False,
                                                            store_type='gkart',
                                                            store_id=store.id,
                                                            store_order_id__in=order_ids):
            for i in o.order_items.all():
                item_key = f'{i.store_order_id}-{i.line_id}'
                # Store order single items can become multiple items (bundles)
                if not unfulfilled_supplement_items.get(item_key):
                    unfulfilled_supplement_items[item_key] = []
                unfulfilled_supplement_items[item_key].append(i)
        return unfulfilled_supplement_items

    def get_product_ids(self, orders):
        product_ids = set()
        for order in orders:
            for item in order.get('line_items', []):
                product_ids.add(safe_int(item['product_id']))

        return list(product_ids)

    def normalize_orders(self, context):
        orders_cache = {}
        store = self.get_store()
        orders = context.get('orders', [])
        groovekart_site = store.get_store_url()
        groovekart_admin = store.get_admin_url().rstrip('/')
        product_ids = self.get_product_ids(orders)
        products_by_source_id = self.get_products_by_source_id(product_ids)
        order_ids = [order['id'] for order in orders]
        order_tracks_by_item = self.get_order_tracks_by_item(order_ids)
        unfulfilled_supplement_items = self.get_unfulfilled_supplement_items(order_ids)
        context['has_print_on_demand'] = False

        for order in orders:
            order_id = order.get('id')
            date_created = self.get_order_date_created(order)
            order['name'] = order_id
            order['date_paid'] = self.get_order_date_paid(order)
            order['date'] = date_created.datetime
            order['date_str'] = date_created.format('MM/DD/YYYY')
            order['date_tooltip'] = date_created.format('YYYY/MM/DD HH:mm:ss')
            order['order_url'] = f'{groovekart_site}/administration/v2/index.php?controller=AdminOrders&id_order={order_id}&vieworder'
            order['store'] = store
            order['placed_orders'] = 0
            order['connected_lines'] = 0
            order['items'] = order.pop('line_items')
            order['lines_count'] = len(order['items'])
            order['shipped'] = order['trackings']['shipped_at'] if order.get('trackings') else False
            order['supplier_types'] = set()
            update_shipstation_items = {}
            shipstation_address_changed = None

            order['pending_payment'] = 'payment error' in order['order_status'].lower()
            order['is_fulfilled'] = order['order_status'] in ['Canceled', 'Refunded', 'Delivered', 'Shipped']
            country_code = order.get('shipping_address', {}).get('country_code')

            for item in order.get('items', []):
                product_id = safe_int(item['product_id'])
                product = products_by_source_id.get(product_id)
                # product_data = product_data_by_source_id.get(product_id)

                variant_id = safe_int(item.get('variants', {}).get('variant_id', '0'))
                item['title'] = item['name']
                item['product'] = product
                item['quantity'] = safe_int(item['quantity'])
                item['total'] = safe_float(item['price'] * item['quantity'])
                item['image'] = item.get('variants', {}).get('image') or item.get('cover_image')
                item['image'] = fix_gkart_image(item['image'])
                item['variant_title'] = ' / '.join([o.get('value') for o in item.get('variants', {}).get('options', [])])
                item['variant_link'] = '{}/v2/index.php/product/form/{}'.format(groovekart_admin, product_id)
                if variant_id == 0:
                    variant_id = -1

                bundle_data = []
                if product:
                    bundles = product.get_bundle_mapping(variant_id)
                    if bundles:
                        product_bundles = []
                        for idx, b in enumerate(bundles):
                            b_product = GrooveKartProduct.objects.filter(id=b['id']).first()
                            if not b_product:
                                continue

                            b_variant_id = b_product.get_real_variant_id(b['variant_id'])
                            b_supplier = b_product.get_supplier_for_variant(b_variant_id)
                            if b_supplier:
                                b_shipping_method = b_product.get_shipping_for_variant(
                                    supplier_id=b_supplier.id,
                                    variant_id=b_variant_id,
                                    country_code=country_code)
                            else:
                                continue

                            b_variant_mapping = b_product.get_variant_mapping(name=b_variant_id, for_extension=True, mapping_supplier=True)
                            if b_variant_id and b_variant_mapping:
                                b_variants = b_variant_mapping
                            else:
                                b_variants = b['variant_title'].split('/') if b['variant_title'] else ''

                            quantity = b['quantity'] * item['quantity']
                            weight = None
                            if b_supplier.user_supplement:
                                weight = b_supplier.user_supplement.get_weight(quantity)

                            product_bundles.append({
                                'product': b_product,
                                'supplier': b_supplier,
                                'shipping_method': b_shipping_method,
                                'quantity': quantity,
                                'weight': weight,
                                'data': b
                            })

                            bundle_data.append({
                                'title': b_product.title,
                                'quantity': quantity,
                                'weight': weight,
                                'product_id': b_product.id,
                                'source_id': b_supplier.get_source_id(),
                                'order_url': app_link('gkart/orders/place', supplier=b_supplier.id, SABundle=True),
                                'variants': b_variants,
                                'shipping_method': b_shipping_method,
                                'country_code': country_code,
                                'supplier_type': b_supplier.supplier_type(),
                            })

                        item['bundles'] = product_bundles
                        item['is_bundle'] = len(bundle_data) > 0
                        order['have_bundle'] = True

                    if product.have_supplier():
                        item['supplier'] = supplier = product.default_supplier
                        is_pls = item['is_pls'] = supplier.is_pls
                        if is_pls:
                            # pass orders without PLS products (when one store is used in multiple account)
                            try:
                                item['weight'] = supplier.user_supplement.get_weight(item['quantity'])
                            except:
                                item['weight'] = False

                            pls_items = unfulfilled_supplement_items.get(f"{order['id']}-{item['id']}")
                            if pls_items:  # Item is not fulfilled yet
                                if shipstation_address_changed is None:  # Check only once
                                    shipstation_address = gkart_customer_address(order, shipstation_fix=True)
                                    address_hash = get_shipstation_address(shipstation_address, hashed=True)
                                    pls_address_hash = pls_items[0].pls_order.shipping_address_hash
                                    shipstation_address_changed = pls_address_hash != str(address_hash)

                                for pls_item in pls_items:
                                    pls_order_id = pls_item.pls_order_id
                                    if not update_shipstation_items.get(pls_order_id):
                                        update_shipstation_items[pls_order_id] = []

                                    # Order items can be placed in different orders at shipstation
                                    update_shipstation_items[pls_order_id].append({
                                        'id': pls_item.line_id,
                                        'quantity': pls_item.quantity,
                                        'title': item['title'],
                                        'sku': pls_item.sku or pls_item.label.user_supplement.shipstation_sku,
                                        'user_supplement_id': pls_item.label.user_supplement.id,
                                        'label_id': pls_item.label_id,
                                        'image_url': item['image'],
                                    })

                        item['is_paid'] = False
                        item['supplier_type'] = supplier.supplier_type()
                        order['supplier_types'].add(item['supplier_type'])
                        order_data = self.get_order_data(order, item, product, supplier)
                        order_data['products'] = bundle_data
                        order_data['is_bundle'] = len(bundle_data) > 0
                        order_data['variant'] = self.get_order_data_variant(item)
                        order_data['weight'] = item.get('weight')
                        order_data['is_refunded'] = order['order_status'] == 'Refunded'
                        order_data_id = order_data['id']
                        item['order_data_id'] = order_data_id
                        item['shipping_method'] = self.get_item_shipping_method(
                            product, item, variant_id, country_code)
                        order['connected_lines'] += 1
                        order_data['shipping_method'] = item['shipping_method']
                        orders_cache['gkart_order_{}'.format(order_data_id)] = order_data
                        item['order_data'] = order_data

                        if supplier.is_dropified_print:
                            context['has_print_on_demand'] = True

                key = '{}_{}'.format(order['id'], item['id'])
                item['order_track'] = order_tracks_by_item.get(key)

            order['mixed_supplier_types'] = len(order['supplier_types']) > 1

            if shipstation_address_changed:
                # Order items can be placed separately at shipstation
                for pls_order_id, line_items in update_shipstation_items.items():
                    update_shipstation_address.apply_async(
                        args=[pls_order_id, self.store.id, 'gkart'],
                        countdown=5
                    )

        bulk_queue = bool(self.request.GET.get('bulk_queue'))
        caches['orders'].set_many(orders_cache, timeout=86400 if bulk_queue else 21600)

        return orders


@method_decorator(login_required, name='dispatch')
@method_decorator(PlatformPermissionRequired('groovekart'), name='dispatch')
class OrdersTrackList(ListView):
    model = GrooveKartOrderTrack
    template_name = 'groovekart/orders_track.html'
    context_object_name = 'orders'
    paginate_by = 20

    def dispatch(self, request, *args, **kwargs):
        if not request.user.can('orders.use'):
            return render(request, 'upgrade.html')

        store = self.get_store()
        if not store:
            messages.warning(request, 'Please add at least one store before using the Tracking page.')
            return HttpResponseRedirect('/gkart/')

        if not request.user.can('place_orders.sub', store):
            messages.warning(request, "You don't have access to this store orders")
            return HttpResponseRedirect('/gkart/')

        return super(OrdersTrackList, self).dispatch(request, *args, **kwargs)

    def get_queryset(self):
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
        days_passed = self.request.GET.get('days_passed', '')
        date = self.request.GET.get('date', '{}-'.format(arrow.get(timezone.now()).replace(days=-30).format('MM/DD/YYYY')))

        store = self.get_store()
        user = self.request.user.models_user
        orders = GrooveKartOrderTrack.objects.select_related('store')
        orders = orders.filter(user=user, store=store)
        orders = orders.defer('data')

        if query:
            date = None
            order_id = order_id_from_name(store, query)

            if order_id:
                query = str(order_id)

            orders = orders.filter(
                Q(order_id=clean_query_id(query))
                | Q(source_id=clean_query_id(query))
                | Q(source_tracking__icontains=query)
            )

        created_at_start, created_at_end = None, None
        if date:
            try:
                daterange_list = date.split('-')

                tz = timezone.localtime(timezone.now()).strftime(' %z')

                created_at_start = arrow.get(daterange_list[0] + tz, r'MM/DD/YYYY Z').datetime

                if len(daterange_list) > 1 and daterange_list[1]:
                    created_at_end = arrow.get(daterange_list[1] + tz, r'MM/DD/YYYY Z')
                    created_at_end = created_at_end.span('day')[1].datetime

            except:
                pass

        if days_passed == 'expired':
            days_passed = self.request.user.get_config('sync_delay_notify_days')
            fulfillment_filter = '0'
            tracking_filter = '0'
            hidden_filter = '0'

        if tracking_filter == '0':
            orders = orders.filter(source_tracking='')
        elif tracking_filter == '1':
            orders = orders.exclude(source_tracking='')

        if fulfillment_filter == '1':
            orders = orders.filter(groovekart_status='fulfilled')
        elif fulfillment_filter == '0':
            orders = orders.exclude(groovekart_status='fulfilled')

        if hidden_filter == '1':
            orders = orders.filter(hidden=True)
        elif not hidden_filter or hidden_filter == '0':
            orders = orders.exclude(hidden=True)

        if completed == '1':
            orders = orders.exclude(source_status='completed')

        if source_reason:
            if source_reason.startswith('_'):
                orders = orders.filter(source_status=source_reason[1:])
            else:
                orders = orders.filter(source_status_details=source_reason)

        errors_list = self.request.GET.getlist('errors')
        if errors_list:

            if 'none' in errors_list:
                errors_list = ['none']
                orders = orders.filter(errors__lte=0).exclude(errors=None)

            elif 'any' in errors_list:
                errors_list = ['any']
                orders = orders.filter(errors__gt=0)

            elif 'pending' in errors_list:
                errors_list = ['pending']
                orders = orders.filter(errors=None)

            else:
                errors = 0
                for i in errors_list:
                    errors |= safe_int(i, 0)

                orders = orders.filter(errors=errors)

        days_passed = safe_int(days_passed)
        if days_passed:
            days_passed = min(days_passed, 30)
            time_threshold = timezone.now() - timezone.timedelta(days=days_passed)
            orders = orders.filter(created_at__lt=time_threshold)

        if created_at_start:
            orders = orders.filter(created_at__gte=created_at_start)

        if created_at_end:
            orders = orders.filter(created_at__lte=created_at_end)

        orders = orders.order_by(sorting)

        error = None
        try:
            orders = get_tracking_orders(store, orders)

        except (requests.exceptions.HTTPError, requests.exceptions.ConnectionError) as e:
            error = f'HTTP Error: {http_excption_status_code(e)}'
        except:
            error = 'Store API Error'
            capture_exception()

        if error:
            messages.error(self.request, f'Error while trying to show your Store Orders: {error}')

        return orders

    def get_context_data(self, **kwargs):
        context = super(OrdersTrackList, self).get_context_data(**kwargs)
        context['store'] = store = self.get_store()
        context['shipping_carriers'] = store_shipping_carriers(store)
        context['groovekart_url'] = store.get_store_url()
        context['breadcrumbs'] = [
            {'title': 'Orders', 'url': reverse('gkart:orders_list')},
            {'title': 'Tracking', 'url': reverse('gkart:orders_track')},
            {'title': store.title, 'url': '{}?store={}'.format(reverse('gkart:orders_list'), store.id)},
        ]

        sync_delay_notify_days = safe_int(self.request.user.get_config('sync_delay_notify_days'))
        sync_delay_notify_highlight = self.request.user.get_config('sync_delay_notify_highlight')
        order_threshold = None
        if sync_delay_notify_days > 0 and sync_delay_notify_highlight:
            order_threshold = timezone.now() - timezone.timedelta(days=sync_delay_notify_days)
        context['order_threshold'] = order_threshold

        context['date'] = None
        if not self.request.GET.get('query'):
            context['date'] = self.request.GET.get('date', '{}-'.format(arrow.get(timezone.now()).replace(days=-30).format('MM/DD/YYYY')))

        return context

    def get_store(self):
        if not hasattr(self, 'store'):
            self.store = get_store_from_request(self.request)

        return self.store


@method_decorator(login_required, name='dispatch')
@method_decorator(PlatformPermissionRequired('groovekart'), name='dispatch')
class OrderPlaceRedirectView(RedirectView):
    permanent = False
    query_string = False

    def dispatch(self, request, *args, **kwargs):
        return super(OrderPlaceRedirectView, self).dispatch(request, *args, **kwargs)

    def get_redirect_url(self, *args, **kwargs):
        if not self.request.user.can('auto_order.use'):
            messages.error(self.request, "Your plan does not allow auto-ordering.")
            return '/gkart/orders'

        if not self.request.GET.get('SAStore'):
            return set_url_query(self.request.get_full_path(), 'SAStore', 'gkart')

        product = None
        supplier = None

        if self.request.GET.get('supplier'):
            supplier = get_object_or_404(GrooveKartSupplier, id=self.request.GET['supplier'])
            permissions.user_can_view(self.request.user, supplier.product)

            product = supplier.short_product_url()

        elif self.request.GET.get('product'):
            product = self.request.GET['product']

            if safe_int(product):
                product = 'https://www.aliexpress.com/item/{}.html'.format(product)

        if not product:
            return Http404("Product or Order not set")

        ali_api_key, ali_tracking_id, user_ali_credentials = get_aliexpress_credentials(self.request.user.models_user)
        admitad_site_id, user_admitad_credentials = get_admitad_credentials(self.request.user.models_user)

        if user_admitad_credentials:
            service = 'admitad'
        elif user_ali_credentials:
            service = 'ali'
        else:
            service = settings.DEFAULT_ALIEXPRESS_AFFILIATE

        disable_affiliate = self.request.user.get_config('_disable_affiliate', False)

        if not disable_affiliate:
            if self.request.user.get_config('_disable_affiliate_permanent'):
                disable_affiliate = True

        redirect_url = False
        if not disable_affiliate:
            if supplier and supplier.is_ebay:
                if not self.request.user.models_user.can('ebay_auto_fulfill.use'):
                    messages.error(self.request, "eBay 1-Click fulfillment is not available on your current plan. "
                                                 "Please upgrade to Premier Plan to use this feature")

                    return '/'

                redirect_url = get_ebay_affiliate_url(product)
            else:
                if service == 'ali' and ali_api_key and ali_tracking_id:
                    redirect_url = get_aliexpress_affiliate_url(ali_api_key, ali_tracking_id, product)

                elif service == 'admitad':
                    redirect_url = get_admitad_affiliate_url(admitad_site_id, product, user=self.request.user)

        if not redirect_url:
            redirect_url = product

        for k in list(self.request.GET.keys()):
            if k.startswith('SA') and k not in redirect_url and self.request.GET[k]:
                redirect_url = affiliate_link_set_query(redirect_url, k, self.request.GET[k])

        redirect_url = affiliate_link_set_query(redirect_url, 'SAStore', 'gkart')

        # Verify if the user didn't pass order limit
        parent_user = self.request.user.models_user
        plan = parent_user.profile.plan
        limit_check_key = 'order_limit_gkart_{}'.format(parent_user.id)
        if cache.get(limit_check_key) is None and plan.auto_fulfill_limit != -1:
            month_start = [i.datetime for i in arrow.utcnow().span('month')][0]
            orders_count = parent_user.groovekartordertrack_set.filter(created_at__gte=month_start).count()

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

            order_data = order_data_cache(f'gkart_{order_key}')
            prefix, store, order, line = order_key.split('_')

        if self.request.user.get_config('extension_version') == '3.41.0':
            # Fix for ePacket selection issue
            shipping_method = self.request.user.models_user.get_config('aliexpress_shipping_method')
            if supplier and supplier.is_aliexpress and 'SACompany' not in self.request.GET and shipping_method and shipping_method != 'EMS_ZX_ZX_US':
                return '{}&SACompany={}'.format(re.sub(r'&$', '', self.request.get_full_path()), shipping_method)

        if order_data:
            order_data['url'] = redirect_url
            caches['orders'].set(order_key, order_data, timeout=caches['orders'].ttl(order_key))

        if order_data and settings.KEEN_PROJECT_ID and not cache.get(event_key):
            try:
                store = GrooveKartStore.objects.get(id=store)
                permissions.user_can_view(self.request.user, store)
            except GrooveKartStore.DoesNotExist:
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
                'store_type': 'GrooveKart',
                'plan': plan.title,
                'plan_id': plan.id,
                'affiliate': affiliate if not disable_affiliate else 'disables',
                'sub_user': self.request.user.is_subuser,
                'extension_version': self.request.user.get_config('extension_version'),
                'total': order_data['total'],
                'quantity': order_data['quantity'],
                'cart': 'SACart' in self.request.GET
            })

            if not settings.DEBUG:
                keen_order_event.delay("auto_fulfill", event_data)

            cache.set(event_key, True, timeout=3600)

        return redirect_url


@method_decorator(login_required, name='dispatch')
@method_decorator(PlatformPermissionRequired('groovekart'), name='dispatch')
class ProfitDashboardView(ProfitDashboardMixin, ListView):
    store_type = 'gkart'
    store_model = GrooveKartStore
    base_template = 'base_groovekart_core.html'


@method_decorator(login_required, name='dispatch')
@method_decorator(PlatformPermissionRequired('groovekart'), name='dispatch')
class ProductMappingView(DetailView):
    model = GrooveKartProduct
    template_name = 'groovekart/product_mapping.html'
    context_object_name = 'product'

    def get_product_suppliers(self, product):
        suppliers = {}
        for supplier in product.get_suppliers():
            suppliers[supplier.id] = {
                'id': supplier.id,
                'name': supplier.get_name(),
                'url': supplier.product_url,
                'source_id': supplier.get_source_id(),
            }

        return suppliers

    def get_current_supplier(self, product):
        pk = self.request.GET.get('supplier') or product.default_supplier.id
        return product.get_suppliers().get(pk=pk)

    def get_variants_map(self, groovekart_product, product, supplier):
        variants_map = product.get_variant_mapping(supplier=supplier)
        variants_map = {key: json.loads(value) for key, value in list(variants_map.items())}

        for variant in groovekart_product.get('variants', []):
            options = GrooveKartProduct.get_variant_options(variant)
            options = [{'title': option} for option in options]
            variants_map.setdefault(str(variant['id']), options)

        return variants_map

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        product = self.object
        groovekart_product = product.sync()
        context['groovekart_product'] = groovekart_product
        context['product'] = product
        context['store'] = product.store
        context['product_id'] = product.id
        context['product_suppliers'] = self.get_product_suppliers(product)
        context['current_supplier'] = current_supplier = self.get_current_supplier(product)
        context['variants_map'] = self.get_variants_map(groovekart_product, product, current_supplier)
        context['breadcrumbs'] = [
            {'title': 'Products', 'url': reverse('gkart:products_list')},
            {'title': product.store.title, 'url': f"{reverse('gkart:products_list')}?store={product.store.id}"},
            {'title': product.title, 'url': reverse('gkart:product_detail', args=[product.id])},
            'Variants Mapping',
        ]

        return context


@method_decorator(login_required, name='dispatch')
@method_decorator(PlatformPermissionRequired('groovekart'), name='dispatch')
class MappingSupplierView(DetailView):
    model = GrooveKartProduct
    template_name = 'groovekart/mapping_supplier.html'
    context_object_name = 'product'

    def get_object(self, queryset=None):
        product = super().get_object(queryset)
        permissions.user_can_view(self.request.user, product)

        return product

    def get_product_suppliers(self, product):
        suppliers = {}
        for supplier in product.get_suppliers():
            suppliers[supplier.id] = {
                'id': supplier.id,
                'name': supplier.get_name(),
                'url': supplier.product_url,
                'source_id': supplier.get_source_id(),
            }

        return suppliers

    def add_supplier_info(self, variants, suppliers_map):
        for index, variant in enumerate(variants):
            default_supplier = {'supplier': self.object.default_supplier.id, 'shipping': {}}
            supplier = suppliers_map.get(str(variant['id']), default_supplier)
            suppliers_map[str(variant['id'])] = supplier
            variants[index]['supplier'] = supplier['supplier']
            variants[index]['shipping'] = supplier['shipping']

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        product = self.object
        groovekart_product = product.sync()
        context['groovekart_product'] = groovekart_product
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
            {'title': 'Products', 'url': reverse('gkart:products_list')},
            {'title': product.store.title, 'url': '{}?store={}'.format(reverse('gkart:products_list'), product.store.id)},
            {'title': product.title, 'url': reverse('gkart:product_detail', args=[product.id])},
            'Advanced Mapping'
        ]

        self.add_supplier_info(groovekart_product.get('variants', []), suppliers_map)

        if not self.request.user.can('suppliers_shipping_mapping.use'):
            shipping_map, mapping_config, suppliers_map = get_mocked_supplier_variants(context['variants_map'])
            context['shipping_map'] = shipping_map
            context['mapping_config'] = mapping_config
            context['suppliers_map'] = suppliers_map
            context['groovekart_product']['variants'] = context['groovekart_product'].get('variants', [])[:5]
            context['upsell'] = True

        return context


class MappingBundleView(DetailView):
    model = GrooveKartProduct
    template_name = 'groovekart/mapping_bundle.html'
    context_object_name = 'product'

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        if not request.user.can('groovekart.use'):
            raise permissions.PermissionDenied()

        return super(MappingBundleView, self).dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super(MappingBundleView, self).get_context_data(**kwargs)
        permissions.user_can_view(self.request.user, self.object)

        product = self.object
        context['api_product'] = product.sync()

        bundle_mapping = []
        for i, v in enumerate(context['api_product']['variants']):
            v['products'] = product.get_bundle_mapping(v['id'], default=[])

            bundle_mapping.append(v)

        context['breadcrumbs'] = [
            {'title': 'Products', 'url': reverse('gkart:products_list')},
            {'title': self.object.store.title, 'url': '{}?store={}'.format(reverse('gkart:products_list'), self.object.store.id)},
            {'title': self.object.title, 'url': reverse('gkart:product_detail', args=[self.object.id])},
            'Bundle Mapping'
        ]

        context.update({
            'store': product.store,
            'product_id': product.id,
            'product': product,
            'bundle_mapping': bundle_mapping,
        })

        context['upsell'] = False
        if not self.request.user.can('mapping_bundle.use'):
            context['upsell'] = True
            context['bundle_mapping'] = get_mocked_bundle_variants(
                context['product'], context['bundle_mapping'])

        return context
