import json
import re
import arrow
import requests
from munch import Munch
from decimal import Decimal

from lib.exceptions import capture_exception

from django.conf import settings
from django.contrib import messages
from django.db.models import Q
from django.views.generic import View, ListView
from django.views.generic.detail import DetailView
from django.views.generic.base import RedirectView
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.contrib.auth.decorators import login_required
from django.urls import reverse, reverse_lazy
from django.core.cache import cache, caches
from django.http import Http404, HttpResponse, HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404, render, redirect
from django.template.defaultfilters import truncatewords
from django.contrib.auth import get_user_model
from django.core.cache.utils import make_template_fragment_key

from aliexpress_core.models import AliexpressAccount
from profits.mixins import ProfitDashboardMixin
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
    aws_s3_context,
    fix_order_data,
    jwt_encode,
    safe_int,
    url_join,
    clean_query_id,
    safe_float,
    safe_json,
    http_excption_status_code,
    order_data_cache,
    format_queueable_orders
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
    get_daterange_filters,
    get_customer_id,
)

from . import utils
from . import tasks
from addons_core.models import Addon
from product_common.utils import get_order_reviews


@login_required
def product_alerts(request):
    store = utils.get_store_from_request(request)
    if not store:
        messages.warning(request, 'Please add at least one store before using the Alerts page.')
        return HttpResponseRedirect('/woo/')

    if not request.user.can('price_changes.use'):
        return render(request, 'woocommerce/product_alerts.html', {
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
        product = get_object_or_404(WooProduct, id=product)
        permissions.user_can_view(request.user, product)

    post_per_page = safe_int(request.user.models_user.get_config('_woo_alerts_ppp')) or settings.ITEMS_PER_PAGE
    page = safe_int(request.GET.get('page'), 1)

    changes = ProductChange.objects.select_related('woo_product') \
                                   .select_related('woo_product__default_supplier') \
                                   .filter(user=request.user.models_user,
                                           woo_product__store=store)

    if request.user.is_subuser:
        store_ids = request.user.profile.subuser_woo_permissions.filter(
            codename='view_alerts'
        ).values_list(
            'store_id', flat=True
        )
        changes = changes.filter(woo_product__store_id__in=store_ids)

    if product:
        changes = changes.filter(woo_product=product)
    else:
        changes = changes.filter(hidden=show_hidden)

    category = request.GET.get('category')
    if category:
        changes = changes.filter(categories__icontains=category)
    product_type = request.GET.get('product_type', '')
    if product_type:
        changes = changes.filter(woo_product__product_type__icontains=product_type)

    changes = changes.order_by('-updated_at')

    paginator = SimplePaginator(changes, post_per_page)
    page = min(max(1, page), paginator.num_pages)
    page = paginator.page(page)
    changes = page.object_list

    products = []
    product_variants = {}
    for i in changes:
        woo_id = i.product.source_id
        if woo_id and str(woo_id) not in products:
            products.append(str(woo_id))
    try:
        if len(products):
            products = utils.get_woo_products(store=store, product_ids=products)
            for p in products:
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
        change['woo_link'] = i.product.woocommerce_url
        change['original_link'] = i.product.get_original_info().get('url')
        p = product_variants.get(str(i.product.source_id), {})

        if not request.user.models_user.get_config('_woo_alerts_variants_fix'):
            p['variants'] = i.product.retrieve_variants()

        variants = p.get('variants', [])
        for c in change['changes']['variants']['quantity']:
            variant_id = 0
            index = variant_index_from_supplier_sku(i.product, c['sku'], variants)
            if index is not None:
                variant_id = variants[index]['id']
            if variant_id > 0:
                if variants[index]['manage_stock']:
                    c['woo_value'] = variants[index]['stock_quantity']
                else:
                    c['woo_value'] = "Unmanaged"
            elif len(variants) == 0 or variant_id < 0:
                if p.get('manage_stock'):
                    c['woo_value'] = p['stock_quantity']
                else:
                    c['woo_value'] = "Unmanaged"
            else:
                c['woo_value'] = "Not Found"
        for c in change['changes']['variants']['price']:
            variant_id = 0
            index = variant_index_from_supplier_sku(i.product, c['sku'], variants)
            if index is not None:
                variant_id = variants[index]['id']
            if variant_id > 0:
                if variants[index].get('price') is not None:
                    c['woo_value'] = variants[index]['price']
                else:
                    c['woo_value_label'] = "Not Found"
            elif (len(variants) == 0 or variant_id < 0) and 'price' in p:
                c['woo_value'] = p['price']
            else:
                c['woo_value_label'] = "Not Found"

        product_changes.append(change)

    # Allow sending notification for new changes
    cache.delete('product_change_%d' % request.user.models_user.id)

    # Delete sidebar alert info cache
    cache.delete(make_template_fragment_key('alert_info', [request.user.id]))

    return render(request, 'woocommerce/product_alerts.html', {
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
            store = WooStore.objects.get(id=request.GET.get('store'))
            permissions.user_can_view(request.user, store)

            product = WooProduct.objects.get(id=request.GET.get('product'))
            permissions.user_can_edit(request.user, product)

            api_product = product.sync()

            first_image = api_product['images'][0] if len(api_product['images']) else ''
            results = []
            if 'variants' in api_product:
                for v in api_product['variants']:
                    results.append({
                        'value': " / ".join(v['variant']),
                        'data': v['id'],
                        'image': v.get('image', {}).get('src', first_image),
                    })

            if not len(results):
                results.append({
                    'value': "Default",
                    'data': -1,
                    'image': first_image
                })

            return JsonResponse({'query': q, 'suggestions': results}, safe=False)

        except WooStore.DoesNotExist:
            return JsonResponse({'error': 'Store not found'}, status=404)

        except WooProduct.DoesNotExist:
            return JsonResponse({'error': 'Product not found'}, status=404)

    elif target == 'types':
        types = []
        for product in request.user.models_user.wooproduct_set.only('product_type').filter(product_type__icontains=q).order_by()[:10]:
            if product.product_type not in types:
                types.append(product.product_type)

        return JsonResponse({'query': q, 'suggestions': [{'value': i, 'data': i} for i in types]}, safe=False)

    elif target == 'title':
        results = []
        products = request.user.models_user.wooproduct_set.only('id', 'title', 'data').filter(title__icontains=q, source_id__gt=0)
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

        try:
            currency_settings = store.wcapi.get('settings/general/woocommerce_currency').json()
            currency_val = currency_settings.get('value')

            if not currency_val:
                currency_val = currency_settings.get('default')

            option = currency_settings['options'][currency_val]
            option = re.findall(r'\((\S+)\)$', option).pop()

            store.currency_format = f'{option} {{{{ amount }}}}'
        except:
            pass

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

        if self.object.store:
            store_title = self.object.store.title
            store_products = '{}?store={}'.format(products, self.object.store.id)
            context['breadcrumbs'].insert(1, {'title': store_title, 'url': store_products})

        context.update(aws_s3_context())

        last_check = None
        try:
            if self.object.monitor_id > 0:
                cache_key = 'woocommerce_product_last_check_{}'.format(self.object.id)
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

        context['alert_config'] = safe_json(self.object.config)

        context['token'] = jwt_encode({'id': self.request.user.id})

        context['upsell_alerts'] = not self.request.user.can('price_changes.use')
        context['config'] = self.request.user.get_config()

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
        context['breadcrumbs'] = [
            {'title': 'Products', 'url': reverse('woo:products_list')},
            {'title': product.store.title, 'url': f"{reverse('woo:products_list')}?store={product.store.id}"},
            {'title': product.title, 'url': reverse('woo:product_detail', args=[product.id])},
            'Variants Mapping',
        ]

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

        if not self.request.user.can('suppliers_shipping_mapping.use'):
            shipping_map, mapping_config, suppliers_map = get_mocked_supplier_variants(context['variants_map'])
            context['shipping_map'] = shipping_map
            context['mapping_config'] = mapping_config
            context['suppliers_map'] = suppliers_map
            context['woocommerce_product']['variants'] = context['woocommerce_product'].get('variants', [])[:5]
            context['upsell'] = True

        return context


class MappingBundleView(DetailView):
    model = WooProduct
    template_name = 'woocommerce/mapping_bundle.html'
    context_object_name = 'product'

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        if not request.user.can('woocommerce.use'):
            raise permissions.PermissionDenied()

        return super(MappingBundleView, self).dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super(MappingBundleView, self).get_context_data(**kwargs)

        product = self.object
        permissions.user_can_view(self.request.user, self.object)

        context['api_product'] = product.sync()

        bundle_mapping = []

        for i, v in enumerate(context['api_product']['variants']):
            v['products'] = product.get_bundle_mapping(v['id'], default=[])

            bundle_mapping.append(v)

        context['breadcrumbs'] = [
            {'title': 'Products', 'url': reverse('woo:products_list')},
            {'title': self.object.store.title, 'url': '{}?store={}'.format(reverse('woo:products_list'), self.object.store.id)},
            {'title': self.object.title, 'url': reverse('woo:product_detail', args=[self.object.id])},
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


class VariantsEditView(DetailView):
    model = WooProduct
    template_name = 'woocommerce/variants_edit.html'
    slug_field = 'source_id'
    slug_url_kwarg = 'pid'

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        if not request.user.can('product_variant_setup.use'):
            return render(request, 'upgrade.html')

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

        self.bulk_queue = bool(request.GET.get('bulk_queue'))
        if self.bulk_queue and not request.user.can('bulk_order.use'):
            return JsonResponse({'error': "Your plan doesn't have Bulk Ordering feature."}, status=402)

        return super(OrdersList, self).dispatch(request, *args, **kwargs)

    # Get temaplte name funcion for TemplateView class
    def get_template_names(self):
        theme = self.request.GET.get('theme')
        if theme:
            self.request.user.set_config('use_old_theme', theme == 'old')

        if self.request.user.get_config('use_old_theme'):
            return ['woocommerce/orders_list_old.html']
        else:
            return ['woocommerce/orders_list.html']

    def get_store(self):
        if not hasattr(self, 'store'):
            self.store = get_store_from_request(self.request)

        return self.store

    def render_to_response(self, context, **response_kwargs):
        if self.bulk_queue:
            return format_queueable_orders(context['orders'], context['page_obj'], store_type='woo', request=self.request)

        return super().render_to_response(context, **response_kwargs)

    def use_db_filters(self, params, filters):
        filtered, woo_orders = utils.orders_after_filters(self.get_store(), params)
        if filtered:
            woo_order_ids = woo_orders.values_list('order_id', flat=True)
            include_ids = woo_order_ids or [0]
            filters['include'] = ','.join([str(id_) for id_ in include_ids])

        return filters

    def use_api_filters(self, params, filters):
        if params.get('status') and not params['status'] == 'any':
            filters['status'] = params['status']

        daterange = params.get('created_at_daterange')
        if daterange and not daterange == 'all':
            filters['after'], filters['before'] = get_daterange_filters(daterange)

        product_id = params.get('query_product')
        if product_id:
            self.product_filter = WooProduct.objects.filter(pk=safe_int(product_id))
            filters['product'] = self.product_filter.first().source_id if self.product_filter else 0

        if params.get('query_customer'):
            filters['customer'] = get_customer_id(self.get_store(), params['query_customer'])
            if filters['customer'] is None:
                filters['customer'] = -9999999999  # A hack to show no orders if a customer is not found.
                # TO DO Show registered customers as a dropdown list to choose from

        return filters

    def get_filters(self):
        filters = {}
        params = self.request.GET
        filters = {}

        if self.sync.store_sync_enabled:
            filters = self.use_db_filters(params, filters)
        else:
            filters = self.use_api_filters(params, filters)

        if params.get('sort') in ['order_date', '!order_date']:
            filters['orderby'] = 'date'
            if params.get('sort') == 'order_date':
                filters['order'] = 'asc'
            if params.get('sort') == '!order_date':
                filters['order'] = 'desc'

        query = params.get('query') or params.get('query_order')
        if query:
            filters['include'] = query.replace('#', '').strip()

        return filters

    def get_queryset(self):
        self.get_sync_status()
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
            capture_exception()

        context['store'] = store = self.get_store()
        context['status'] = self.request.GET.get('status', 'any')
        context['shipping_carriers'] = store_shipping_carriers(store)
        context['created_at_daterange'] = self.request.GET.get('created_at_daterange', '')
        context['product_filter'] = getattr(self, 'product_filter', None)
        context['countries'] = get_counrties_list()
        context['use_aliexpress_api'] = self.request.user.models_user.can('aliexpress_api_integration.use')
        context['use_extension_quick'] = self.request.user.models_user.can('aliexpress_extension_quick_order.use')
        context['aliexpress_account'] = AliexpressAccount.objects.filter(user=self.request.user.models_user)

        # getting total orders
        context['total_orders'] = self.request.user.profile.get_orders_count(WooOrderTrack)
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

        context['breadcrumbs'] = [
            {'title': page_title, 'url': self.url},
            {'title': store.title, 'url': '{}?store={}'.format(self.url, store.id)}]

        try:
            if not api_error:
                self.normalize_orders(context)
        except (requests.exceptions.HTTPError, requests.exceptions.ConnectionError) as e:
            api_error = f'HTTP Error: {http_excption_status_code(e)}'
        except:
            api_error = 'Store API Error'
            capture_exception()

        if api_error:
            messages.error(self.request, f'Error while trying to show your Store Orders: {api_error}')

        admitad_site_id, user_admitad_credentials = get_admitad_credentials(self.request.user.models_user)
        context['admitad_site_id'] = admitad_site_id if user_admitad_credentials else False

        context['api_error'] = api_error
        context.update(**self.get_sync_status())

        return context

    def get_product_supplier(self, product, variant_id=None):
        if product.have_supplier():
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

    def get_sync_status(self):
        if not hasattr(self, 'sync'):
            self.sync = Munch()
            store = self.get_store()

            if self.request.GET.get('old') == '1':
                store.disable_sync()
            elif self.request.GET.get('old') == '0':
                store.enable_sync()

            self.sync.store_order_synced = store.is_synced()
            self.sync.store_sync_enabled = self.sync.store_order_synced \
                and (store.is_sync_enabled() or self.request.GET.get('new')) \
                and not self.request.GET.get('live')

            if self.sync.store_sync_enabled:
                if store.get_sync_status().sync_status in [0, 6]:
                    messages.info(self.request, 'Your store orders are being imported.')

            orders_sync_check_key = f'woo_store_orders_sync_check_{self.store.id}'
            if self.sync.store_sync_enabled and cache.get(orders_sync_check_key) is None:
                cache.set(orders_sync_check_key, True, timeout=43200)
                tasks.sync_woo_orders.apply_async(args=[self.store.id], expires=600)

        return self.sync

    def get_order_data(self, order, item, product, supplier, logistics_address=None):
        store = self.get_store()
        models_user = self.request.user.models_user
        aliexpress_fix_address = models_user.get_config('aliexpress_fix_address', True)
        aliexpress_fix_city = models_user.get_config('aliexpress_fix_city', True)
        german_umlauts = models_user.get_config('_use_german_umlauts', False)

        country = order['shipping']['country'] or order['billing']['country']

        _order, shipping_address = woo_customer_address(
            order=order,
            aliexpress_fix=aliexpress_fix_address and supplier and supplier.is_aliexpress,
            aliexpress_fix_city=aliexpress_fix_city,
            german_umlauts=german_umlauts,
            shipstation_fix=supplier.is_pls if supplier else False)

        return {
            'id': '{}_{}_{}'.format(store.id, order['id'], item['id']),
            'order_name': order['number'],
            'title': item['title'],
            'quantity': item['quantity'],
            'shipping_address': shipping_address,
            'logistics_address': logistics_address,
            'order_id': order['id'],
            'line_id': item['id'],
            'product_id': product.id,
            'product_source_id': product.source_id,
            'source_id': supplier.get_source_id() if supplier else None,
            'supplier_id': supplier.get_store_id() if supplier else None,
            'supplier_type': supplier.supplier_type() if supplier else None,
            'total': safe_float(item['price'], 0.0),
            'store': store.id,
            'order': {
                'phone': {
                    'number': order['billing'].get('phone'),
                    'country': country,
                },
                'note': models_user.get_config('order_custom_note'),
                'epacket': bool(models_user.get_config('epacket_shipping')),
                'aliexpress_shipping_method': models_user.get_config('aliexpress_shipping_method'),
                'auto_mark': bool(models_user.get_config('auto_ordered_mark', True)),  # Auto mark as Ordered
            },
        }

    def get_raw_order_data(self, order, item, logistics_address):
        store = self.get_store()
        country = order['shipping']['country'] or order['billing']['country']

        return {
            'id': '{}_{}_{}'.format(store.id, order['id'], item['id']),
            'order_name': order['number'],
            'title': item['title'],
            'quantity': item['quantity'],
            'logistics_address': logistics_address,
            'order_id': order['id'],
            'line_id': item['id'],
            'product_id': item['product_id'],
            'variants': item['name'].split(' - ')[1:],
            'total': safe_float(item['price'], 0.0),
            'store': store.id,
            'is_raw': True,
            'order': {
                'phone': {
                    'number': order['billing'].get('phone'),
                    'country': country,
                },
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
        for attribute in data.get('attributes', []):
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
        if not product_ids:
            self.product_data = {}

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

    def get_unfulfilled_supplement_items(self, order_ids):
        store = self.get_store()
        unfulfilled_supplement_items = {}
        for o in PLSOrder.objects.prefetch_related('order_items',
                                                   'order_items__label',
                                                   'order_items__label__user_supplement',
                                                   ).filter(is_fulfilled=False,
                                                            store_type='woo',
                                                            store_id=store.id,
                                                            store_order_id__in=order_ids):
            for i in o.order_items.all():
                item_key = f'{i.store_order_id}-{i.line_id}'
                # Store order single items can become multiple items (bundles)
                if not unfulfilled_supplement_items.get(item_key):
                    unfulfilled_supplement_items[item_key] = []
                unfulfilled_supplement_items[item_key].append(i)
        return unfulfilled_supplement_items

    def normalize_orders(self, context):
        orders_cache = {}
        raw_orders_cache = {}
        store = self.get_store()
        admin_url = store.get_admin_url()
        orders = context.get('orders', [])
        product_ids = self.get_product_ids(orders)
        product_by_source_id = self.get_product_by_source_id(product_ids)
        product_data = self.get_product_data(product_ids)
        order_ids = self.get_order_ids(orders)
        order_track_by_item = self.get_order_track_by_item(order_ids)
        unfulfilled_supplement_items = self.get_unfulfilled_supplement_items(order_ids)
        context['has_print_on_demand'] = False

        for order in orders:
            order_id = order.get('id')
            country_code = order['shipping']['country'] or order['billing']['country']
            date_created = self.get_order_date_created(order)
            order['name'] = order_id
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
            order['supplier_types'] = set()
            order['pending_payment'] = 'pending' in order['status'].lower()
            order['is_fulfilled'] = order['status'] in ['cancelled', 'refunded', 'completed', 'trash']
            update_shipstation_items = {}
            shipstation_address_changed = None
            refunded_amounts = [Decimal(r['total']) * -1 for r in order['refunds']]

            for item in order.get('items'):
                self.update_placed_orders(order, item)
                product_id = item['product_id']
                product = product_by_source_id.get(product_id)
                data = product_data.get(product_id)
                item['title'] = item['name']
                item['variations'] = [m.get('display_value')
                                      for m in item['meta_data']
                                      if isinstance(m.get('display_value'), str)
                                      and m.get('display_value') in item['name']]
                item['product'] = product
                item['image'] = next(iter(data['images']), {}).get('src') if data else None
                variant_id = item.get('variation_id')
                if variant_id == 0:
                    variant_id = -1

                logistics_address = None
                models_user = self.request.user.models_user
                if models_user.can('logistics.use'):
                    logistics_address = woo_customer_address(
                        order=order,
                        german_umlauts=models_user.get_config('_use_german_umlauts', False),
                        shipstation_fix=True)[1]

                    if not product or not product.have_supplier():
                        raw_order_data_id = f"raw_{store.id}_{order['id']}_{item['id']}"
                        item['raw_order_data_id'] = raw_order_data_id
                        raw_orders_cache[f"woo_order_{raw_order_data_id}"] = self.get_raw_order_data(order, item, logistics_address)

                bundle_data = []
                if product:
                    bundles = product.get_bundle_mapping(variant_id)
                    if bundles:
                        product_bundles = []
                        for idx, b in enumerate(bundles):
                            b_product = WooProduct.objects.filter(id=b['id']).first()
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
                                'order_url': app_link('woo/orders/place', supplier=b_supplier.id, SABundle=True),
                                'variants': b_variants,
                                'shipping_method': b_shipping_method,
                                'country_code': country_code,
                                'supplier_type': b_supplier.supplier_type(),
                            })

                        item['bundles'] = product_bundles
                        item['is_bundle'] = len(bundle_data) > 0
                        order['have_bundle'] = True

                    if product.have_supplier():
                        supplier = self.get_product_supplier(product, variant_id)
                        order_data = self.get_order_data(order, item, product, supplier, logistics_address=logistics_address)
                        order_data['products'] = bundle_data
                        order_data['is_bundle'] = len(bundle_data) > 0
                        order_data['variant'] = self.get_order_data_variant(product, item)
                        # TODO: search for item total in order refunded amounts is not accurate but refunds API might slow the page
                        order_data['is_refunded'] = order['status'] == 'refunded' or item['total'] in refunded_amounts
                        order_data_id = order_data['id']
                        attributes = [variant['title'] for variant in order_data['variant']]
                        item['attributes'] = ', '.join(attributes)
                        item['order_data_id'] = order_data_id
                        item['supplier'] = supplier
                        item['supplier_type'] = supplier.supplier_type()
                        order['supplier_types'].add(supplier.supplier_type())
                        item['shipping_method'] = self.get_item_shipping_method(product, item, variant_id, country_code)
                        order_data['shipping_method'] = item['shipping_method']

                        is_pls = item['is_pls'] = supplier.is_pls
                        if is_pls:
                            item['is_paid'] = False

                            # pass orders without PLS products (when one store is used in multiple account)
                            try:
                                item['weight'] = supplier.user_supplement.get_weight(item['quantity'])
                                order_data['weight'] = item['weight']
                            except:
                                item['weight'] = False

                            pls_items = unfulfilled_supplement_items.get(f"{order['id']}-{item['id']}")
                            if pls_items:  # Item is not fulfilled yet
                                if shipstation_address_changed is None:  # Check only once
                                    get_config = self.request.user.models_user.get_config
                                    shipstation_address = woo_customer_address(
                                        order,
                                        german_umlauts=get_config('_use_german_umlauts', False),
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
                                        'title': item['title'],
                                        'sku': pls_item.sku or pls_item.label.user_supplement.shipstation_sku,
                                        'user_supplement_id': pls_item.label.user_supplement.id,
                                        'label_id': pls_item.label_id,
                                        'image_url': item['image'],
                                    })

                        order_data = fix_order_data(self.request.user, order_data)
                        orders_cache['woo_order_{}'.format(order_data_id)] = order_data
                        item['order_data'] = order_data

                        if supplier.is_dropified_print:
                            context['has_print_on_demand'] = True

                key = '{}_{}_{}'.format(order['id'], item['id'], item['product_id'])
                item['order_track'] = order_track_by_item.get(key)
                if item['order_track']:
                    order['tracked_lines'] += 1

            order['mixed_supplier_types'] = len(order['supplier_types']) > 1
            if order['tracked_lines'] != 0 and \
                    order['tracked_lines'] < order['lines_count'] and \
                    order['placed_orders'] < order['lines_count']:
                order['partially_ordered'] = True

            if shipstation_address_changed:
                # Order items can be placed separately at shipstation
                for pls_order_id, line_items in update_shipstation_items.items():
                    update_shipstation_address.apply_async(
                        args=[pls_order_id, self.store.id, 'woo'],
                        countdown=5
                    )

        caches['orders'].set_many(orders_cache, timeout=86400 if self.bulk_queue else 21600)
        caches['orders'].set_many(raw_orders_cache, timeout=86400 if self.bulk_queue else 21600)


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

    def get_paginate_by(self, queryset):
        custom_limit = safe_int(self.request.user.get_config('_woo_order_track_limit'), None)
        if custom_limit:
            return custom_limit if custom_limit > 10 else 10

        return self.paginate_by

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

        orders = WooOrderTrack.objects.select_related('store', 'user', 'user__profile') \
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

            try:
                context['orders'] = get_tracking_products(self.get_store(), context['orders'], self.paginate_by)
            except Exception as e:
                capture_exception(extra=utils.http_exception_response(e))

            context['shipping_carriers'] = store_shipping_carriers(self.get_store())

        except (requests.exceptions.HTTPError, requests.exceptions.ConnectionError) as e:
            error = f'HTTP Error: {http_excption_status_code(e)}'
        except:
            error = 'Store API Error'
            capture_exception()

        if error:
            messages.error(self.request, f'Error while trying to show your Store Orders: {error}')

        context['api_error'] = error

        sync_delay_notify_days = safe_int(self.request.user.get_config('sync_delay_notify_days'))
        sync_delay_notify_highlight = self.request.user.get_config('sync_delay_notify_highlight')
        order_threshold = None
        if sync_delay_notify_days > 0 and sync_delay_notify_highlight:
            order_threshold = timezone.now() - timezone.timedelta(days=sync_delay_notify_days)
        context['order_threshold'] = order_threshold

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
        context['use_aliexpress_api'] = self.request.user.models_user.can('aliexpress_api_integration.use')
        context['aliexpress_account_count'] = AliexpressAccount.objects.filter(user=self.request.user.models_user).count()

        context['rejected_status'] = ALIEXPRESS_REJECTED_STATUS

        context['orders'] = get_order_reviews(self.request.user.models_user, context['orders'])
        return context

    def get_store(self):
        if not hasattr(self, 'store'):
            self.store = get_store_from_request(self.request)

        return self.store


class BoardsList(ListView):
    model = WooBoard
    context_object_name = 'boards'
    template_name = 'woocommerce/boards_list.html'
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

        user_boards_list = self.request.user.models_user.wooboard_set.all()
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
        if not self.request.user.can('auto_order.use'):
            messages.error(self.request, "Your plan does not allow auto-ordering.")
            return '/woo/orders'

        if not self.request.GET.get('SAStore'):
            return set_url_query(self.request.get_full_path(), 'SAStore', 'woo')

        product = None
        supplier = None
        disable_affiliate = self.request.user.get_config('_disable_affiliate', False)

        if self.request.GET.get('nff'):
            disable_affiliate = True

        if self.request.GET.get('supplier'):
            supplier = get_object_or_404(WooSupplier, id=self.request.GET['supplier'])
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

        redirect_url = affiliate_link_set_query(redirect_url, 'SAStore', 'woo')

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
            orders_count = parent_user.profile.get_orders_count(WooOrderTrack)

            if not settings.DEBUG and not auto_fulfill_limit or orders_count + 1 > auto_fulfill_limit:
                messages.error(self.request,
                               "Woohoo! 🎉. You are growing and you've hit your orders limit for this month."
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

            order_data = order_data_cache(f'woo_{order_key}')
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
@method_decorator(PlatformPermissionRequired('woocommerce'), name='dispatch')
class ProfitDashboardView(ProfitDashboardMixin, ListView):
    store_type = 'woo'
    store_model = WooStore
    base_template = 'base_woocommerce_core.html'
