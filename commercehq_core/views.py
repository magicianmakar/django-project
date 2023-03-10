import re
import arrow
import simplejson as json
import requests

from lib.exceptions import capture_exception

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.cache import cache, caches
from django.urls import reverse
from django.db.models import Q
from django.http import HttpResponse, Http404
from django.http import JsonResponse, HttpResponseRedirect
from django.shortcuts import render, get_object_or_404, redirect
from django.template.defaultfilters import truncatewords
from django.utils.decorators import method_decorator
from django.utils import timezone
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_http_methods
from django.views.generic import ListView
from django.views.generic.base import RedirectView
from django.views.generic.detail import DetailView
from django.core.cache.utils import make_template_fragment_key

from aliexpress_core.models import AliexpressAccount
from supplements.lib.shipstation import get_address as get_shipstation_address
from supplements.models import PLSOrder
from supplements.tasks import update_shipstation_address
from shopified_core import permissions
from shopified_core.decorators import PlatformPermissionRequired
from shopified_core.mocks import (
    get_mocked_bundle_variants,
    get_mocked_supplier_variants,
    get_mocked_alert_changes,
)
from shopified_core.paginators import SimplePaginator
from shopified_core.shipping_helper import get_counrties_list
from shopified_core.utils import (
    ALIEXPRESS_REJECTED_STATUS,
    app_link,
    fix_order_data,
    jwt_encode,
    safe_int,
    safe_float,
    aws_s3_context,
    url_join,
    http_exception_response,
    clean_query_id,
    http_excption_status_code,
    order_data_cache,
    format_queueable_orders,
)
from shopified_core.tasks import keen_order_event
from product_alerts.models import ProductChange
from product_alerts.utils import variant_index_from_supplier_sku
from profits.mixins import ProfitDashboardMixin
from leadgalaxy.utils import (
    get_aliexpress_credentials,
    get_admitad_credentials,
    get_aliexpress_affiliate_url,
    get_admitad_affiliate_url,
    get_ebay_affiliate_url,
    affiliate_link_set_query,
    set_url_query
)

from .forms import CommerceHQStoreForm
from .decorators import no_subusers, must_be_authenticated, ajax_only
from .models import (
    CommerceHQStore,
    CommerceHQProduct,
    CommerceHQBoard,
    CommerceHQOrderTrack,
    CommerceHQSupplier
)
from .utils import (
    CommerceHQOrdersPaginator,
    get_store_from_request,
    commercehq_products,
    chq_customer_address,
    get_tracking_orders,
    order_id_from_name,
    store_shipping_carriers,
    get_orders_filter,
    get_chq_product
)

from . import utils
from addons_core.models import Addon
from product_common.utils import get_order_reviews


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

    return render(request, 'commercehq/partial/store_update_form.html', {'form': form})


@login_required
def product_alerts(request):
    store = utils.get_store_from_request(request)
    if not store:
        messages.warning(request, 'Please add at least one store before using the Alerts page.')
        return HttpResponseRedirect('/chq/')

    if not request.user.can('price_changes.use'):
        return render(request, 'commercehq/product_alerts.html', {
            'upsell': True,
            'product_changes': get_mocked_alert_changes(),
            'page': 'product_alerts',
            'store': store,
            'breadcrumbs': ['Alerts'],
            'selected_menu': 'products:alerts',
        })

    show_hidden = bool(request.GET.get('hidden'))

    product = request.GET.get('product')
    if product:
        product = get_object_or_404(CommerceHQProduct, id=product)
        permissions.user_can_view(request.user, product)

    post_per_page = settings.ITEMS_PER_PAGE
    page = safe_int(request.GET.get('page'), 1)

    changes = ProductChange.objects.select_related('chq_product') \
                                   .select_related('chq_product__default_supplier') \
                                   .filter(user=request.user.models_user,
                                           chq_product__store=store)

    if request.user.is_subuser:
        store_ids = request.user.profile.subuser_chq_permissions.filter(
            codename='view_alerts'
        ).values_list(
            'store_id', flat=True
        )
        changes = changes.filter(chq_product__store_id__in=store_ids)

    if product:
        changes = changes.filter(chq_product=product)
    else:
        changes = changes.filter(hidden=show_hidden)

    category = request.GET.get('category')
    if category:
        changes = changes.filter(categories__icontains=category)
    product_type = request.GET.get('product_type', '')
    if product_type:
        changes = changes.filter(chq_product__product_type__icontains=product_type)

    changes = changes.order_by('-updated_at')

    paginator = SimplePaginator(changes, post_per_page)
    page = min(max(1, page), paginator.num_pages)
    page = paginator.page(page)
    changes = page.object_list

    products = []
    product_variants = {}
    for i in changes:
        chq_id = i.product.get_chq_id()
        if chq_id and str(chq_id) not in products:
            products.append(str(chq_id))
    try:
        if len(products):
            products = utils.get_chq_products(store=store, product_ids=products, expand='variants')
            for p in products:
                if p.get('id') is not None:
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
        change['chq_link'] = i.product.commercehq_url
        change['original_link'] = i.product.get_original_info().get('url')
        p = product_variants.get(str(i.product.get_chq_id()), {})
        variants = p.get('variants', None)
        for c in change['changes']['variants']['quantity']:
            if variants is not None:
                index = variant_index_from_supplier_sku(i.product, c['sku'], variants)
                if index is not None:
                    # TODO: check track_inventory status
                    if p.get('track_inventory'):
                        quantity = 'Not Supported'
                        c['chq_value'] = quantity
                    else:
                        c['chq_value'] = "Unmanaged"
                else:
                    c['chq_value'] = "Not Found"
            elif p.get('is_multi') is False:
                if p.get('track_inventory'):
                    quantity = 'Not Supported'
                    c['chq_value'] = quantity
                else:
                    c['chq_value'] = "Unmanaged"
            else:
                c['chq_value'] = "Not Found"
        for c in change['changes']['variants']['price']:
            if variants is not None:
                index = variant_index_from_supplier_sku(i.product, c['sku'], variants)
                if index is not None:
                    c['chq_value'] = variants[index]['price']
                else:
                    c['chq_value_label'] = "Not Found"
            elif p.get('is_multi') is False:
                c['chq_value'] = p['price']
            else:
                c['chq_value_label'] = "Not Found"

        product_changes.append(change)

    # Allow sending notification for new changes
    cache.delete('product_change_%d' % request.user.models_user.id)

    # Delete sidebar alert info cache
    cache.delete(make_template_fragment_key('alert_info', [request.user.id]))

    return render(request, 'commercehq/product_alerts.html', {
        'product_changes': product_changes,
        'show_hidden': show_hidden,
        'product': product,
        'paginator': paginator,
        'current_page': page,
        'page': 'product_alerts',
        'store': store,
        'category': category,
        'product_type': product_type,
        'breadcrumbs': ['Alerts'],
    })


class BoardsList(ListView):
    model = CommerceHQBoard
    context_object_name = 'boards'
    template_name = 'commercehq/boards_list.html'
    paginator_class = SimplePaginator
    paginate_by = 12

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        if not request.user.can('view_product_boards.sub'):
            raise permissions.PermissionDenied()

        return super(BoardsList, self).dispatch(request, *args, **kwargs)

    def get_queryset(self):
        qs = super(BoardsList, self).get_queryset()
        qs = qs.filter(user=self.request.user.models_user)
        search_title = self.request.GET.get('search') or None
        if search_title is not None:
            qs = qs.filter(title__icontains=search_title)
        return qs

    def get_context_data(self, **kwargs):
        context = super(BoardsList, self).get_context_data(**kwargs)
        user_boards_list = self.request.user.models_user.commercehqboard_set.all()
        paginator = SimplePaginator(user_boards_list, 12)
        page = safe_int(self.request.GET.get('page'), 1)
        current_page = paginator.page(page)

        for board in current_page.object_list:
            board.saved = board.saved_count(request=self.request)
            board.connected = board.connected_count(request=self.request)
        context['boards'] = current_page
        context['breadcrumbs'] = ['Boards']

        return context


class BoardDetailView(DetailView):
    model = CommerceHQBoard
    context_object_name = 'board'
    template_name = 'commercehq/board.html'

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

        products = commercehq_products(self.request, store=None, board=self.object.id)
        paginator = SimplePaginator(products, 25)
        page = safe_int(self.request.GET.get('page'), 1)
        page = paginator.page(page)

        context['paginator'] = paginator
        context['products'] = page
        context['current_page'] = page
        context['breadcrumbs'] = [{'title': 'Boards', 'url': reverse('chq:boards_list')}, self.object.title]

        return context


class ProductsList(ListView):
    model = CommerceHQProduct
    template_name = 'commercehq/products_grid.html'
    context_object_name = 'products'

    paginator_class = SimplePaginator
    paginate_by = 25

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        if not request.user.can('commercehq.use'):
            raise permissions.PermissionDenied()

        return super(ProductsList, self).dispatch(request, *args, **kwargs)

    def get_queryset(self):
        return commercehq_products(self.request)

    def get_context_data(self, **kwargs):
        context = super(ProductsList, self).get_context_data(**kwargs)

        context['breadcrumbs'] = [{'title': 'Products', 'url': reverse('chq:products_list')}]

        if self.request.GET.get('store', 'n') == 'n':
            context['breadcrumbs'].append({'title': 'Non Connected', 'url': reverse('chq:products_list') + '?store=n'})
        elif self.request.GET.get('store', 'n') == 'c':
            context['breadcrumbs'].append({'title': 'Connected', 'url': reverse('chq:products_list') + '?store=c'})
        elif safe_int(self.request.GET.get('store')):
            store = CommerceHQStore.objects.get(id=self.request.GET.get('store'))
            permissions.user_can_view(self.request.user, store)

            context['store'] = store
            context['breadcrumbs'].append({'title': store.title, 'url': '{}?store={}'.format(reverse('chq:products_list'), store.id)})

        return context


class ProductDetailView(DetailView):
    model = CommerceHQProduct
    template_name = 'commercehq/product_detail.html'
    context_object_name = 'product'

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        if not request.user.can('commercehq.use'):
            raise permissions.PermissionDenied()

        return super(ProductDetailView, self).dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super(ProductDetailView, self).get_context_data(**kwargs)

        permissions.user_can_view(self.request.user, self.object)

        context['product_data'] = self.object.parsed

        if self.object.source_id:
            context['commercehq_product'] = self.object.sync()
            context['product_data'] = self.object.parsed
            if context['commercehq_product']:
                context['product_data']['images'] = self.object.get_common_images()
            else:
                messages.error(self.request, "Product Not Found in CommerceHQ")

        context['breadcrumbs'] = [
            {'title': 'Products', 'url': reverse('chq:products_list')}
        ]

        if self.object.store:
            context['breadcrumbs'].append({
                'title': self.object.store.title,
                'url': '{}?store={}'.format(reverse('chq:products_list'), self.object.store.id)
            })

        context['breadcrumbs'].append(self.object.title)

        context.update(aws_s3_context())

        last_check = None
        try:
            if self.object.monitor_id > 0:
                cache_key = 'chq_product_last_check_{}'.format(self.object.id)
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


class ProductMappingView(DetailView):
    model = CommerceHQProduct
    template_name = 'commercehq/product_mapping.html'
    context_object_name = 'product'

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        if not request.user.can('commercehq.use'):
            raise permissions.PermissionDenied()

        return super(ProductMappingView, self).dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super(ProductMappingView, self).get_context_data(**kwargs)

        product = self.object
        permissions.user_can_view(self.request.user, self.object)

        context['commercehq_product'] = product.sync()

        images_map = {}
        for option in context['commercehq_product']['options']:
            for thumb in option['thumbnails']:
                if thumb.get('image'):
                    images_map[thumb['value']] = thumb['image']['path']

        for idx, variant in enumerate(context['commercehq_product']['variants']):
            for v in variant['variant']:
                if v in images_map:
                    context['commercehq_product']['variants'][idx]['image'] = images_map[v]
                    continue

            if len(variant['images']):
                context['commercehq_product']['variants'][idx]['image'] = variant['images'][0]

        current_supplier = self.request.GET.get('supplier')
        if not current_supplier and product.default_supplier:
            current_supplier = product.default_supplier.id

        current_supplier = product.get_suppliers().get(id=current_supplier)

        variants_map = product.get_variant_mapping(supplier=current_supplier)

        seen_variants = []

        for i, v in enumerate(context['commercehq_product']['variants']):
            mapped = variants_map.get(str(v['id']))
            if mapped:
                options = mapped
            else:
                options = [{'title': a} for a in v['variant']]

            try:
                if type(options) not in [list, dict]:
                    options = json.loads(options)

                    if type(options) is int:
                        options = str(options)
            except:
                pass

            variants_map[str(v['id'])] = options
            context['commercehq_product']['variants'][i]['default'] = options
            seen_variants.append(str(v['id']))

        for k in list(variants_map.keys()):
            if k not in seen_variants:
                del variants_map[k]

        product_suppliers = {}
        for i in product.get_suppliers():
            product_suppliers[i.id] = {
                'id': i.id,
                'name': i.get_name(),
                'url': i.product_url,
                'source_id': i.get_source_id(),
            }

        context['breadcrumbs'] = [
            {'title': 'Products', 'url': reverse('chq:products_list')},
            {'title': self.object.store.title, 'url': '{}?store={}'.format(reverse('chq:products_list'), self.object.store.id)},
            {'title': self.object.title, 'url': reverse('chq:product_detail', args=[self.object.id])},
            'Variants Mapping'
        ]

        context.update({
            'store': product.store,
            'product_id': product.id,
            'product': product,
            'variants_map': variants_map,
            'product_suppliers': product_suppliers,
            'current_supplier': current_supplier,
        })

        return context


class MappingSupplierView(DetailView):
    model = CommerceHQProduct
    template_name = 'commercehq/mapping_supplier.html'
    context_object_name = 'product'

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        if not request.user.can('commercehq.use'):
            raise permissions.PermissionDenied()

        return super(MappingSupplierView, self).dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super(MappingSupplierView, self).get_context_data(**kwargs)

        product = self.object
        permissions.user_can_view(self.request.user, self.object)

        context['commercehq_product'] = product.sync()

        images_map = {}
        for option in context['commercehq_product']['options']:
            for thumb in option['thumbnails']:
                if thumb.get('image'):
                    images_map[thumb['value']] = thumb['image']['path']

        for idx, variant in enumerate(context['commercehq_product']['variants']):
            for v in variant['variant']:
                if v in images_map:
                    context['commercehq_product']['variants'][idx]['image'] = images_map[v]
                    continue

            if len(variant['images']):
                context['commercehq_product']['variants'][idx]['image'] = variant['images'][0]

        suppliers_map = product.get_suppliers_mapping()
        default_supplier_id = product.default_supplier.id
        for i, v in enumerate(context['commercehq_product']['variants']):
            supplier = suppliers_map.get(str(v['id']), {'supplier': default_supplier_id, 'shipping': {}})
            suppliers_map[str(v['id'])] = supplier

            context['commercehq_product']['variants'][i]['supplier'] = supplier['supplier']
            context['commercehq_product']['variants'][i]['shipping'] = supplier['shipping']

        product_suppliers = {}
        for i in product.get_suppliers():
            product_suppliers[i.id] = {
                'id': i.id,
                'name': i.get_name(),
                'url': i.product_url,
                'source_id': i.get_source_id(),
            }

        context['breadcrumbs'] = [
            {'title': 'Products', 'url': reverse('chq:products_list')},
            {'title': self.object.store.title, 'url': '{}?store={}'.format(reverse('chq:products_list'), self.object.store.id)},
            {'title': self.object.title, 'url': reverse('chq:product_detail', args=[self.object.id])},
            'Advanced Mapping'
        ]

        context.update({
            'store': product.store,
            'product_id': product.id,
            'product': product,

            'suppliers_map': suppliers_map,
            'product_suppliers': product_suppliers,
            'shipping_map': product.get_shipping_mapping(),
            'variants_map': product.get_all_variants_mapping(),
            'mapping_config': product.get_mapping_config(),

            'countries': get_counrties_list(),
        })

        if not self.request.user.can('suppliers_shipping_mapping.use'):
            shipping_map, mapping_config, suppliers_map = get_mocked_supplier_variants(context['variants_map'])
            context['shipping_map'] = shipping_map
            context['mapping_config'] = mapping_config
            context['suppliers_map'] = suppliers_map
            context['commercehq_product']['variants'] = context['commercehq_product']['variants'][:5]
            context['upsell'] = True

        return context


class MappingBundleView(DetailView):
    model = CommerceHQProduct
    template_name = 'commercehq/mapping_bundle.html'
    context_object_name = 'product'

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        if not request.user.can('commercehq.use'):
            raise permissions.PermissionDenied()

        return super(MappingBundleView, self).dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super(MappingBundleView, self).get_context_data(**kwargs)

        product = self.object
        permissions.user_can_view(self.request.user, self.object)

        context['commercehq_product'] = product.sync()

        images_map = {}
        for option in context['commercehq_product']['options']:
            for thumb in option['thumbnails']:
                if thumb.get('image'):
                    images_map[thumb['value']] = thumb['image']['path']

        for idx, variant in enumerate(context['commercehq_product']['variants']):
            for v in variant['variant']:
                if v in images_map:
                    context['commercehq_product']['variants'][idx]['image'] = images_map[v]
                    continue

            if len(variant['images']):
                context['commercehq_product']['variants'][idx]['image'] = variant['images'][0]

        bundle_mapping = []

        for i, v in enumerate(context['commercehq_product']['variants']):
            v['products'] = product.get_bundle_mapping(v['id'], default=[])

            bundle_mapping.append(v)

        context['breadcrumbs'] = [
            {'title': 'Products', 'url': reverse('chq:products_list')},
            {'title': self.object.store.title, 'url': '{}?store={}'.format(reverse('chq:products_list'), self.object.store.id)},
            {'title': self.object.title, 'url': reverse('chq:product_detail', args=[self.object.id])},
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


class OrdersList(ListView):
    model = CommerceHQProduct
    template_name = 'commercehq/orders_list.html'

    paginator_class = CommerceHQOrdersPaginator
    paginate_by = 20

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        if not self.get_store():
            messages.warning(request, 'Please add at least one store before using the Orders page.')
            return redirect('chq:index')

        if not request.user.can('place_orders.sub', self.get_store()):
            messages.warning(request, "You don't have access to this store orders")
            return redirect('chq:index')

        bulk_queue = bool(request.GET.get('bulk_queue'))
        if bulk_queue and not request.user.can('bulk_order.use'):
            return JsonResponse({'error': "Your plan doesn't have Bulk Ordering feature."}, status=402)

        if not request.user.can('commercehq.use'):
            raise permissions.PermissionDenied()

        return super(OrdersList, self).dispatch(request, *args, **kwargs)

    def render_to_response(self, context, **response_kwargs):
        bulk_queue = bool(self.request.GET.get('bulk_queue'))
        if bulk_queue:
            return format_queueable_orders(context['orders'], context['page_obj'], store_type='chq', request=self.request)

        return super().render_to_response(context, **response_kwargs)

    def get_queryset(self):
        return []

    def get_paginator(self, *args, **kwargs):
        paginator = super(OrdersList, self).get_paginator(*args, **kwargs)
        paginator.set_store(self.get_store())

        if self.request.GET.get('reset') == '1':
            self.request.user.profile.del_config_values('_chq_orders_filter_', True)

        self.filter_data = {
            'query': self.request.GET.get('query'),
            'fulfillment': get_orders_filter(self.request, 'fulfillment', '0,1,2,4'),
            'financial': get_orders_filter(self.request, 'financial', '1'),
            'sort': get_orders_filter(self.request, 'sort', '!order_date'),
        }

        created_at_daterange = self.request.GET.get('created_at_daterange', 'all')
        if not self.filter_data['query'] and created_at_daterange:
            try:
                daterange_list = created_at_daterange.split('-')

                tz = timezone.localtime(timezone.now()).strftime(' %z')

                self.filter_data['order_date'] = {}
                self.filter_data['order_date']['start'] = arrow.get(daterange_list[0] + tz, r'MM/DD/YYYY Z').timestamp
                self.filter_data['order_date']['start'] = str(self.filter_data['order_date']['start'])

                if len(daterange_list) > 1 and daterange_list[1]:
                    created_at_end = arrow.get(daterange_list[1] + tz, r'MM/DD/YYYY Z')
                    self.filter_data['order_date']['end'] = created_at_end.span('day')[1].timestamp
                    self.filter_data['order_date']['end'] = str(self.filter_data['order_date']['end'])

            except:
                pass

        if self.filter_data['query']:
            self.filter_data['fulfillment'] = 'any'
            self.filter_data['financial'] = 'any'

        paginator.set_request(self.request)
        paginator.set_filter(**self.filter_data)

        return paginator

    def get_context_data(self, **kwargs):
        context = {}
        api_error = None

        try:
            context = super(OrdersList, self).get_context_data(**kwargs)
        except (requests.exceptions.HTTPError, requests.exceptions.ConnectionError) as e:
            api_error = f'HTTP Error: {http_excption_status_code(e)}'
        except:
            api_error = 'Store API Error'
            capture_exception()

        context['store'] = self.get_store()

        # getting total orders
        context['total_orders'] = self.request.user.profile.get_orders_count(CommerceHQOrderTrack)
        context['autofulfill_limit'] = self.request.user.profile.get_auto_fulfill_limit()

        try:
            context['autofulfill_usage_percent'] = safe_float(context['total_orders']) / safe_float(
                context['autofulfill_limit'])
        except:
            context['autofulfill_usage_percent'] = 0
        if context['autofulfill_usage_percent'] > 0.8:
            context['autofulfill_addons'] = Addon.objects.filter(auto_fulfill_limit__gt=0, is_active=True).all()

        if context['autofulfill_limit'] != -1:
            page_title = 'Orders ({}/{})'.format(context['total_orders'], context['autofulfill_limit'])
        else:
            page_title = 'Orders'

        context['breadcrumbs'] = [{
            'title': page_title,
            'url': reverse('chq:orders_list')
        }, {
            'title': context['store'].title,
            'url': '{}?store={}'.format(reverse('chq:orders_list'), context['store'].id)
        }]

        try:
            if not api_error:
                context['orders'] = self.get_orders(context)
                context['shipping_carriers'] = store_shipping_carriers(self.get_store())

        except (requests.exceptions.HTTPError, requests.exceptions.ConnectionError) as e:
            api_error = f'HTTP Error: {http_excption_status_code(e)}'
        except:
            api_error = 'Store API Error'
            capture_exception()

        context['user_filter'] = get_orders_filter(self.request)

        context.update(self.filter_data)

        context['aliexpress_mobile_order'] = self.request.user.models_user.can('aliexpress_mobile_order.use')
        context['order_debug'] = self.request.session.get('is_hijacked_user') or \
            (self.request.user.is_superuser and self.request.GET.get('debug')) or \
            self.request.user.get_config('_orders_debug') or settings.DEBUG

        if api_error:
            messages.error(self.request, f'Error while trying to show your Store Orders: {api_error}')

        context['created_at_daterange'] = self.request.GET.get('created_at_daterange', 'all')
        context['use_aliexpress_api'] = self.request.user.models_user.can('aliexpress_api_integration.use')
        context['use_extension_quick'] = self.request.user.models_user.can('aliexpress_extension_quick_order.use')
        context['aliexpress_account'] = AliexpressAccount.objects.filter(user=self.request.user.models_user)
        context['api_error'] = api_error

        admitad_site_id, user_admitad_credentials = get_admitad_credentials(self.request.user.models_user)
        context['admitad_site_id'] = admitad_site_id if user_admitad_credentials else False

        return context

    def get_store(self):
        if not hasattr(self, 'store'):
            self.store = get_store_from_request(self.request)

        return self.store

    def get_orders(self, ctx):
        store = self.get_store()
        models_user = self.request.user.models_user
        fix_order_variants = self.request.user.get_config('fix_order_variants')
        aliexpress_fix_address = models_user.get_config('aliexpress_fix_address', True)
        aliexpress_fix_city = models_user.get_config('aliexpress_fix_city', True)
        german_umlauts = models_user.get_config('_use_german_umlauts', False)

        products_cache = {}
        orders_cache = {}
        raw_orders_cache = {}

        orders_ids = []
        products_ids = []
        orders_list = {}
        unfulfilled_supplement_items = {}

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

        for o in PLSOrder.objects.prefetch_related('order_items',
                                                   'order_items__label',
                                                   'order_items__label__user_supplement',
                                                   ).filter(is_fulfilled=False,
                                                            store_type='chq',
                                                            store_id=self.store.id,
                                                            store_order_id__in=orders_ids):
            for i in o.order_items.all():
                item_key = f'{i.store_order_id}-{i.line_id}'
                # Store order single items can become multiple items (bundles)
                if not unfulfilled_supplement_items.get(item_key):
                    unfulfilled_supplement_items[item_key] = []
                unfulfilled_supplement_items[item_key].append(i)

        ctx['has_print_on_demand'] = False
        for odx, order in enumerate(orders):
            created_at = arrow.get(order['order_date'])
            try:
                created_at = created_at.to(self.request.session['django_timezone'])
            except:
                pass

            order['name'] = order['display_number']
            order['date'] = created_at
            order['date_str'] = created_at.format('MM/DD/YYYY')
            order['date_tooltip'] = created_at.format('YYYY/MM/DD HH:mm:ss')
            order['order_url'] = self.store.get_admin_url('admin', 'orders', order['id'])
            order['order_api_url'] = self.store.get_api_url('orders', order['id'])
            order['order_api_url'] = order['order_api_url'].replace('https://', 'https://{}:{}@'.format(self.store.api_key, self.store.api_password))

            order['store'] = self.store
            order['placed_orders'] = 0
            order['connected_lines'] = 0
            order['lines_count'] = len(order['items'])
            order['refunded_lines'] = []
            order['supplier_types'] = set()

            order_status = {
                0: 'Not sent to fulfillment',
                1: 'Partially sent to fulfillment',
                2: 'Partially sent to fulfillment & shipped',
                3: 'Sent to fulfillment',
                4: 'Partially shipped',
                5: 'Shipped',
            }

            paid_status = {
                0: 'Not paid',
                1: 'Paid',
                -1: 'Partially refunded',
                -2: 'Fully refunded',
            }

            order['fulfillment_status'] = order_status.get(order['status'])
            order['financial_status'] = paid_status.get(order['paid'])

            # In case order['payment']['type'] == None
            is_paypal = 'paypal' in (order.get('payment', {}).get('type') or '').lower()
            is_pending_payment = safe_int(order['paid']) == 0
            order['pending_payment'] = is_pending_payment and is_paypal
            order['is_fulfilled'] = order['status'] >= 3
            update_shipstation_items = {}
            shipstation_address_changed = None

            if not order['address']:
                order['address'] = {
                    'shipping': {}
                }
            order['shipping_address'] = order['address']['shipping']

            for fulfilment in order['fulfilments']:
                for item in fulfilment['items']:
                    orders_cache['chq_fulfilments_{}_{}_{}'.format(self.store.id, order['id'], item['id'])] = fulfilment['id']

            tracked_unfulfilled = []

            for ldx, line in enumerate(order['items']):
                line.update(line.get('data'))
                line.update(line.get('status'))

                variant_id = line.get('variant', {}).get('id')
                if line['product_id'] is None and '-' in line['title']:
                    match_titles = '-'.join(line['title'].split('-')[0:-1]).strip()
                    if match_titles in products_cache:
                        if products_cache[match_titles]:
                            line['product_id'] = products_cache[match_titles].source_id
                    else:
                        match_product = CommerceHQProduct.objects.filter(store=self.store, title=match_titles, source_id__gt=0).first()
                        products_cache[match_titles] = match_product

                        if match_product:
                            line['product_id'] = match_product.source_id

                line['variant_link'] = self.store.get_admin_url('admin/products/view?id={}'.format(line['product_id']))

                if variant_id:
                    line['variant_link'] += '&variant={}'.format(variant_id)

                if not variant_id and not line['is_multi']:
                    variant_id = -1

                line['refunded'] = line['id'] in order['refunded_lines']

                line['image'] = (line.get('image') or '').replace('/uploads/', '/uploads/thumbnail_')

                line['order_track'] = orders_list.get('{}-{}'.format(order['id'], line['id']))

                if line['order_track'] and line['not_fulfilled'] > 0:
                    tracked_unfulfilled.append({'id': line['id'], 'quantity': line['not_fulfilled']})

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
                bundle_data = []
                country_code = order['address']['shipping'].get('country')

                if models_user.can('logistics.use'):
                    logistics_address = chq_customer_address(
                        order=order,
                        german_umlauts=german_umlauts,
                        shipstation_fix=True)[1]
                else:
                    logistics_address = None

                if product and product.have_supplier():
                    variant_id = product.get_real_variant_id(variant_id)
                    supplier = product.get_supplier_for_variant(variant_id)
                    if supplier:
                        shipping_method = product.get_shipping_for_variant(
                            supplier_id=supplier.id,
                            variant_id=variant_id,
                            country_code=country_code)
                    else:
                        shipping_method = None

                    line['product'] = product
                    line['supplier'] = supplier
                    is_pls = line['is_pls'] = supplier.is_pls
                    if is_pls:
                        line['is_paid'] = False
                        # pass orders without PLS products (when one store is used in multiple account)
                        try:
                            line['weight'] = supplier.user_supplement.get_weight(line['quantity'])
                        except:
                            line['weight'] = False

                        pls_items = unfulfilled_supplement_items.get(f"{order['id']}-{line['id']}")
                        if pls_items:  # Item is not fulfilled yet
                            if shipstation_address_changed is None:  # Check only once
                                shipstation_address = chq_customer_address(
                                    order,
                                    german_umlauts=german_umlauts,
                                    shipstation_fix=True
                                )[1]
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
                                    'title': line['title'],
                                    'sku': pls_item.sku or pls_item.label.user_supplement.shipstation_sku,
                                    'user_supplement_id': pls_item.label.user_supplement.id,
                                    'label_id': pls_item.label_id,
                                    'image_url': line['image'],
                                })

                    line['supplier_type'] = supplier.supplier_type()
                    line['shipping_method'] = shipping_method
                    order['connected_lines'] += 1

                    if supplier:
                        order['supplier_types'].add(supplier.supplier_type())

                    if fix_order_variants:
                        mapped = product.get_variant_mapping(name=variant_id, for_extension=True, mapping_supplier=True)
                        if not mapped:
                            utils.fix_order_variants(self.store, order, product)

                else:
                    raw_order_data_id = f"raw_{store.id}_{order['id']}_{line['id']}"
                    line['raw_order_data_id'] = raw_order_data_id
                    raw_orders_cache[f"chq_order_{raw_order_data_id}"] = {
                        'id': '{}_{}_{}'.format(self.store.id, order['id'], line['id']),
                        'order_name': order['id'],
                        'title': line['title'],
                        'quantity': line['quantity'],
                        'logistics_address': logistics_address,
                        'order_id': order['id'],
                        'line_id': line['id'],
                        'product_id': line['product_id'],
                        'variants': line.get('variant', {}).get('variant', ''),
                        'total': safe_float(line['price'], 0.0),
                        'store': self.store.id,
                        'is_raw': True,
                        'order': {
                            'phone': {
                                'number': order['address'].get('phone'),
                                'country': order['address']['shipping'].get('country')
                            },
                        },
                        'is_refunded': line['refunded']
                    }

                if product:
                    bundles = product.get_bundle_mapping(variant_id)
                    if bundles:
                        product_bundles = []
                        for idx, b in enumerate(bundles):
                            b_product = CommerceHQProduct.objects.filter(id=b['id']).first()
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

                            quantity = b['quantity'] * line['quantity']
                            weight = None
                            if b_supplier.user_supplement:
                                weight = b_supplier.user_supplement.get_weight(quantity)

                            product_bundles.append({
                                'product': b_product,
                                'supplier': b_supplier,
                                'shipping_method': b_shipping_method,
                                'quantity': quantity,
                                'variant': b_variants,
                                'weight': weight,
                                'data': b
                            })

                            bundle_data.append({
                                'title': b_product.title,
                                'quantity': quantity,
                                'weight': weight,
                                'product_id': b_product.id,
                                'source_id': b_supplier.get_source_id(),
                                'order_url': app_link('chq/orders/place', supplier=b_supplier.id, SABundle=True),
                                'variants': b_variants,
                                'shipping_method': b_shipping_method,
                                'country_code': country_code,
                                'supplier_type': b_supplier.supplier_type(),
                            })

                        order['items'][ldx]['bundles'] = product_bundles
                        order['items'][ldx]['is_bundle'] = len(bundle_data) > 0
                        order['have_bundle'] = True

                products_cache[line['product_id']] = product

                _order, customer_address = chq_customer_address(
                    order=order,
                    aliexpress_fix=aliexpress_fix_address,
                    aliexpress_fix_city=aliexpress_fix_city,
                    german_umlauts=german_umlauts,
                    shipstation_fix=supplier.is_pls if supplier else False)

                order['customer_address'] = customer_address

                if not order.get('shipping_address') or order['pending_payment']:
                    order['items'][ldx] = line
                    continue

                order_data = {
                    'id': '{}_{}_{}'.format(self.store.id, order['id'], line['id']),
                    'order_name': order['id'],
                    'title': line['title'],
                    'quantity': line['quantity'],
                    'weight': line.get('weight'),
                    'logistics_address': logistics_address,
                    'shipping_address': customer_address,
                    'shipping_method': line.get('shipping_method'),
                    'order_id': order['id'],
                    'line_id': line['id'],
                    'product_id': product.id if product else None,
                    'source_id': supplier.get_source_id() if supplier else None,
                    'supplier_id': supplier.get_store_id() if supplier else None,
                    'supplier_type': supplier.supplier_type() if supplier else None,
                    'total': safe_float(line['price'], 0.0),
                    'store': self.store.id,
                    'order': {
                        'phone': {
                            'number': order['address'].get('phone'),
                            'country': customer_address['country_code']
                        },
                        'note': models_user.get_config('order_custom_note'),
                        'epacket': bool(models_user.get_config('epacket_shipping')),
                        'aliexpress_shipping_method': models_user.get_config('aliexpress_shipping_method'),
                        'auto_mark': bool(models_user.get_config('auto_ordered_mark', True)),  # Auto mark as Ordered
                    },
                    'is_refunded': line['refunded'],
                    'products': bundle_data,
                    'is_bundle': len(bundle_data) > 0
                }

                if product:
                    mapped = product.get_variant_mapping(name=variant_id, for_extension=True, mapping_supplier=True)
                    if variant_id and mapped:
                        order_data['variant'] = mapped
                    else:
                        order_data['variant'] = line.get('variant', {}).get('variant', '')

                if product and product.have_supplier():
                    order_data = fix_order_data(self.request.user, order_data)
                    orders_cache['order_{}'.format(order_data['id'])] = order_data
                    line['order_data_id'] = order_data['id']

                    line['order_data'] = order_data

                    if supplier.is_dropified_print:
                        ctx['has_print_on_demand'] = True

                order['items'][ldx] = line

            order['order_complete'] = order['placed_orders'] == len(order['items'])

            if tracked_unfulfilled:
                try:
                    fulfilments_url = store.get_api_url('orders', order['id'], 'fulfilments')

                    r = store.request.post(url=fulfilments_url, json={'items': tracked_unfulfilled})
                    r.raise_for_status()
                except Exception as e:
                    capture_exception(level='warning', extra=http_exception_response(e))

            order['mixed_supplier_types'] = len(order['supplier_types']) > 1

            if shipstation_address_changed:
                # Order items can be placed separately at shipstation
                for pls_order_id, line_items in update_shipstation_items.items():
                    update_shipstation_address.apply_async(
                        args=[pls_order_id, self.store.id, 'chq'],
                        countdown=5
                    )

            orders[odx] = order

        bulk_queue = bool(self.request.GET.get('bulk_queue'))
        caches['orders'].set_many(orders_cache, timeout=86400 if bulk_queue else 21600)
        caches['orders'].set_many(raw_orders_cache, timeout=86400 if bulk_queue else 21600)

        return orders


def autocomplete(request, target):
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'User login required'})

    q = request.GET.get('query', '').strip()
    if not q:
        q = request.GET.get('term', '').strip()

    if not q:
        return JsonResponse({'query': q, 'suggestions': []}, safe=False)

    if target == 'variants':
        try:
            store = CommerceHQStore.objects.get(id=request.GET.get('store'))
            permissions.user_can_view(request.user, store)

            product = CommerceHQProduct.objects.get(id=request.GET.get('product'))
            permissions.user_can_edit(request.user, product)

            chq_product = get_chq_product(store, product.source_id)

            images_map = {}
            if 'options' in chq_product:
                for option in chq_product['options']:
                    for thumb in option['thumbnails']:
                        if thumb.get('image'):
                            images_map[thumb['value']] = thumb['image']['path']

            results = []
            if 'variants' in chq_product:
                for idx, variant in enumerate(chq_product['variants']):
                    for v in variant['variant']:
                        if v in images_map:
                            chq_product['variants'][idx]['image'] = images_map[v]
                            continue

                    if len(variant['images']):
                        chq_product['variants'][idx]['image'] = variant['images'][0]['path']

                for v in chq_product['variants']:
                    image = ''
                    if 'image' in v:
                        image = v['image']
                    else:
                        if len(chq_product['images']):
                            image = chq_product['images'][0]['path']

                    if len(chq_product['images']):
                        image = chq_product['images'][0]['path']

                    results.append({
                        'value': " / ".join(v['variant']),
                        'data': v['id'],
                        'image': image,
                    })

            if not len(results):
                image = ''
                if len(chq_product['images']):
                    image = chq_product['images'][0]['path']
                results.append({
                    'value': "Default",
                    'data': -1,
                    'image': image
                })

            return JsonResponse({'query': q, 'suggestions': results}, safe=False)

        except CommerceHQStore.DoesNotExist:
            return JsonResponse({'error': 'Store not found'}, status=404)

        except CommerceHQProduct.DoesNotExist:
            return JsonResponse({'error': 'Product not found'}, status=404)

    elif target == 'title':
        results = []
        products = request.user.models_user.commercehqproduct_set.only('id', 'title', 'data').filter(title__icontains=q, source_id__gt=0)
        store = request.GET.get('store')
        if store:
            products = products.filter(store=store)

        for product in products[:10]:
            results.append({
                'value': (truncatewords(product.title, 10) if request.GET.get('trunc') else product.title),
                'data': product.id,
                'image': product.get_image()
            })

        return JsonResponse({'query': q, 'suggestions': results}, safe=False)

    else:
        return JsonResponse({'error': 'Unknown target'})


class OrderPlaceRedirectView(RedirectView):
    permanent = False
    query_string = False

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        if not request.user.can('commercehq.use'):
            raise permissions.PermissionDenied()

        return super(OrderPlaceRedirectView, self).dispatch(request, *args, **kwargs)

    def get_redirect_url(self, *args, **kwargs):
        if not self.request.user.can('auto_order.use'):
            messages.error(self.request, "Your plan does not allow auto-ordering.")
            return '/chq/orders'

        if not self.request.GET.get('SAStore'):
            return set_url_query(self.request.get_full_path(), 'SAStore', 'chq')

        product = None
        supplier = None
        disable_affiliate = self.request.user.get_config('_disable_affiliate', False)

        if self.request.GET.get('nff'):
            disable_affiliate = True

        if self.request.GET.get('supplier'):
            supplier = get_object_or_404(CommerceHQSupplier, id=self.request.GET['supplier'])
            permissions.user_can_view(self.request.user, supplier.product)

            product = supplier.short_product_url()

        elif self.request.GET.get('product'):
            product = self.request.GET['product']

            if safe_int(product):
                product = 'https://www.aliexpress.com/item/{}.html'.format(product)

        if not product:
            return Http404("Product or Order not set")

        if self.request.GET.get('m'):
            product = product.replace('www.aliexpress.com', 'm.aliexpress.com')

        ali_api_key, ali_tracking_id, user_ali_credentials = get_aliexpress_credentials(self.request.user.models_user)
        admitad_site_id, user_admitad_credentials = get_admitad_credentials(self.request.user.models_user)

        if user_admitad_credentials:
            service = 'admitad'
        elif user_ali_credentials:
            service = 'ali'
        else:
            service = settings.DEFAULT_ALIEXPRESS_AFFILIATE

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

        redirect_url = affiliate_link_set_query(redirect_url, 'SAStore', 'chq')

        # quick extension ordering url rewrite
        if self.request.GET.get('quick-order'):
            if not self.request.user.models_user.can('aliexpress_extension_quick_order.use'):
                messages.error(self.request, "Extension Quick Ordering is not available on your current plan. "
                                             "Please upgrade to use this feature")
                return '/'
            # redirect to shoppping cart directly
            redirect_url = 'https://www.aliexpress.com/p/trade/confirm.html?objectId=' + self.request.GET.get('objectId') + \
                           '&skuId=' + self.request.GET.get('skuId') + '&quantity=' + self.request.GET.get('quantity') + \
                           '&SAConfirmOrder=' + self.request.GET.get('SAPlaceOrder') + '&quick-order=1'

        # Verify if the user didn't pass order limit
        parent_user = self.request.user.models_user
        plan = parent_user.profile.plan

        auto_fulfill_limit = parent_user.profile.get_auto_fulfill_limit()
        if auto_fulfill_limit != -1:
            orders_count = parent_user.profile.get_orders_count(CommerceHQOrderTrack)

            if not settings.DEBUG and not auto_fulfill_limit or orders_count + 1 > auto_fulfill_limit:
                messages.error(self.request,
                               "Woohoo! ????. You are growing and you've hit your orders limit for this month."
                               " Upgrade now to keep placing orders or wait until next "
                               "month for your limit to reset.")
                return '/'

        # Save Auto fulfill event
        event_data = {}
        order_data = None
        order_key = self.request.GET.get('SAPlaceOrder')
        if order_key:
            event_key = 'keen_event_{}'.format(self.request.GET['SAPlaceOrder'])

            if not order_key.startswith('order_'):
                order_key = 'order_{}'.format(order_key)

            order_data = order_data_cache(order_key)
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
                store = CommerceHQStore.objects.get(id=store)
                permissions.user_can_view(self.request.user, store)
            except CommerceHQStore.DoesNotExist:
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
                'store_type': 'CommerceHQ',
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


class OrdersTrackList(ListView):
    model = CommerceHQOrderTrack
    paginator_class = SimplePaginator
    template_name = 'commercehq/orders_track.html'
    context_object_name = 'orders'
    paginate_by = 20

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        if not self.get_store():
            messages.warning(request, 'Please add at least one store before using the Tracking page.')
            return redirect('chq:index')

        if not request.user.can('commercehq.use'):
            raise permissions.PermissionDenied()

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

        sorting = self.request.GET.get('sort', 'update')
        order_desc = self.request.GET.get('desc', 'true')
        if sorting:
            if order_desc == 'true':
                sorting = f"-{sorting}"
        sorting = order_map.get(sorting, 'status_updated_at')

        query = self.request.GET.get('query')
        tracking_filter = self.request.GET.get('tracking')
        fulfillment_filter = self.request.GET.get('fulfillment')
        hidden_filter = self.request.GET.get('hidden')
        completed = self.request.GET.get('completed')
        source_reason = self.request.GET.get('reason')

        store = self.get_store()

        orders = CommerceHQOrderTrack.objects.select_related('store', 'user', 'user__profile') \
                                             .filter(user=self.request.user.models_user, store=store)

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

        try:
            context['orders'] = get_tracking_orders(self.get_store(), context['orders'])
            context['shipping_carriers'] = store_shipping_carriers(self.get_store())
        except:
            pass

        sync_delay_notify_days = safe_int(self.request.user.get_config('sync_delay_notify_days'))
        sync_delay_notify_highlight = self.request.user.get_config('sync_delay_notify_highlight')
        order_threshold = None
        if sync_delay_notify_days > 0 and sync_delay_notify_highlight:
            order_threshold = timezone.now() - timezone.timedelta(days=sync_delay_notify_days)
        context['order_threshold'] = order_threshold

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

        context['use_aliexpress_api'] = self.request.user.models_user.can('aliexpress_api_integration.use')
        context['aliexpress_account_count'] = AliexpressAccount.objects.filter(user=self.request.user.models_user).count()
        context['rejected_status'] = ALIEXPRESS_REJECTED_STATUS

        context['orders'] = get_order_reviews(self.request.user.models_user, context['orders'])
        return context

    def get_store(self):
        if not hasattr(self, 'store'):
            self.store = get_store_from_request(self.request)

        return self.store


@method_decorator(login_required, name='dispatch')
@method_decorator(PlatformPermissionRequired('commercehq'), name='dispatch')
class ProfitDashboardView(ProfitDashboardMixin, ListView):
    store_type = 'chq'
    store_model = CommerceHQStore
    base_template = 'base_commercehq_core.html'
