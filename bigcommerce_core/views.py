import json
import re

import arrow
import jwt
import requests

from raven.contrib.django.raven_compat.models import client as raven_client

from django.conf import settings
from django.contrib import messages
from django.db.models import Q
from django.views.generic import ListView
from django.views.generic.detail import DetailView
from django.views.generic.base import RedirectView
from django.views.decorators.clickjacking import xframe_options_exempt
# from django.utils import timezone
from django.utils.decorators import method_decorator
from django.contrib.auth.decorators import login_required
from django.urls import reverse, reverse_lazy
from django.core.cache import cache, caches
from django.http import Http404, JsonResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, render, redirect
from django.core.cache.utils import make_template_fragment_key
from bigcommerce.api import BigcommerceApi

from shopified_core import permissions
from shopified_core.paginators import SimplePaginator
from shopified_core.shipping_helper import get_counrties_list
from shopified_core.utils import (
    ALIEXPRESS_REJECTED_STATUS,
    app_link,
    aws_s3_context,
    safe_int,
    url_join,
    clean_query_id,
    safe_float,
    http_excption_status_code,
    order_data_cache,
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

from .models import BigCommerceStore, BigCommerceProduct, BigCommerceSupplier, BigCommerceOrderTrack, BigCommerceBoard
from .utils import (
    bigcommerce_products,
    store_shipping_carriers,
    get_store_from_request,
    BigCommerceListPaginator,
    BigCommerceListQuery,
    order_id_from_name,
    get_tracking_orders,
    get_tracking_products,
    get_order_line_fulfillment_status,
    bigcommerce_customer_address,
    get_product_data,
    get_order_product_data,
    get_order_shipping_addresses,
)

from . import utils


@login_required
@xframe_options_exempt
def auth(request):
    code = request.GET['code']
    context = request.GET['context']
    scope = request.GET['scope']
    store_hash = context.split('/')[1]
    redirect = request.build_absolute_uri('/bigcommerce/auth')
    redirect = redirect.replace('http://', 'https://')

    try:
        client = BigcommerceApi(client_id=settings.BIGCOMMERCE_CLIENT_ID, store_hash=store_hash)
        token = client.oauth_fetch_token(settings.BIGCOMMERCE_CLIENT_SECRET, code, context, scope, redirect)
    except Exception:
        messages.error(request, 'Failed to Get Access Token')
        return render(request, 'home/index.html')

    user = request.user
    if user.is_subuser:
        messages.error(request, 'Sub-Users can not add new stores')
        return render(request, 'home/index.html')

    can_add, total_allowed, user_count = permissions.can_add_store(user)

    if not can_add:
        if user.profile.plan.is_free and user.can_trial():
            from shopify_oauth.views import subscribe_user_to_default_plan

            subscribe_user_to_default_plan(user)
        else:
            raven_client.captureMessage(
                'Add Extra BigCommerce Store',
                level='warning',
                extra={
                    'user': user.email,
                    'plan': user.profile.plan.title,
                    'stores': user.profile.get_bigcommerce_stores().count()
                }
            )

            if user.profile.plan.is_free or user.can_trial():
                url = request.build_absolute_uri('/user/profile#plan')
                messages.error(request, 'Please Activate your account first by visiting:\n{}')
                return render(request, 'home/index.html')
            else:
                messages.error(request, ('Your plan does not support connecting another BigCommerce store. '
                              'Please contact support@dropified.com to learn how to connect '
                              'more stores.'))
                return render(request, 'home/index.html')

    access_token = token['access_token']
    client = BigcommerceApi(client_id=settings.BIGCOMMERCE_CLIENT_ID, store_hash=store_hash, access_token=access_token)
    bigcommerce_store = client.Store.all()

    store = BigCommerceStore()
    store.user = user.models_user
    store.title = bigcommerce_store.name
    store.api_url = bigcommerce_store.domain
    store.api_key = store_hash
    store.api_token = access_token

    permissions.user_can_add(user, store)
    store.save()

    messages.success(request, 'Your store was successfully installed.')
    return render(request, 'home/index.html')


@login_required
@xframe_options_exempt
def load(request):
    signed_payload = request.GET['signed_payload']
    authorised = BigcommerceApi.oauth_verify_payload(signed_payload, settings.BIGCOMMERCE_CLIENT_SECRET)
    if authorised:
        store_hash = authorised['store_hash']
        try:
            store = BigCommerceStore.objects.get(api_key=store_hash, is_active=True)

            if not permissions.user_can_view(request.user, store, raise_on_error=False, superuser_can=False):
                messages.error(reqeust, 'You don\'t have access to this store')
                return render(request, 'home/index.html')

            messages.success(request, 'Your store was successfully installed.');
            return render(request, 'home/index.html')

        except BigCommerceStore.DoesNotExist:
            messages.error(request, 'Couldn\'t find this store')
            return render(request, 'home/index.html')
        # except BigCommerceStore.MultipleObjectsReturned:
        #     # TODO: Handle multi stores
        #     raven_client.captureException()
        # except:
        #     raven_client.captureException()

    messages.error(request, 'Verification failed')
    return render(request, 'home/index.html')


@xframe_options_exempt
def uninstall(request):
    pass
    # signed_payload = request.GET['signed_payload']
    # authorised = BigcommerceApi.oauth_verify_payload(signed_payload, settings.BIGCOMMERCE_CLIENT_SECRET)
    # if authorised:
    #     store_hash = authorised['store_hash']
    #     try:
    #         store = BigCommerceStore.objects.get(api_key=store_hash, is_active=True)

    #         from product_alerts.utils import unmonitor_store

    #         store.is_active = False
    #         store.uninstalled_at = timezone.now()
    #         store.save()

    #         unmonitor_store(store)
    #         return render(request, 'bigcommerce/message.html', {
    #             'message': 'The Store Successfully Uninstalled.',
    #         })

    #     except BigCommerceStore.DoesNotExist:
    #         return render(request, 'bigcommerce/message.html', {
    #             'error': 'Couldn\'t find this store',
    #         })
    #     # except BigCommerceStore.MultipleObjectsReturned:
    #     #     # TODO: Handle multi stores
    #     #     raven_client.captureException()
    #     # except:
    #     #     raven_client.captureException()

    # return render(request, 'bigcommerce/message.html', {
    #     'error': 'Verification failed',
    # })


@login_required
def product_alerts(request):
    if not request.user.can('price_changes.use'):
        return render(request, 'upgrade.html', {'selected_menu': 'products:alerts'})

    show_hidden = True if request.GET.get('hidden') else False

    product = request.GET.get('product')
    if product:
        product = get_object_or_404(BigCommerceProduct, id=product)
        permissions.user_can_view(request.user, product)

    post_per_page = settings.ITEMS_PER_PAGE
    page = safe_int(request.GET.get('page'), 1)

    store = utils.get_store_from_request(request)
    if not store:
        messages.warning(request, 'Please add at least one store before using the Alerts page.')
        return HttpResponseRedirect('/bigcommerce/')

    changes = ProductChange.objects.select_related('bigcommerce_product') \
                                   .select_related('bigcommerce_product__default_supplier') \
                                   .filter(user=request.user.models_user,
                                           bigcommerce_product__store=store)

    if request.user.is_subuser:
        store_ids = request.user.profile.subuser_bigcommerce_permissions.filter(
            codename='view_alerts'
        ).values_list(
            'store_id', flat=True
        )
        changes = changes.filter(bigcommerce_product__store_id__in=store_ids)

    if product:
        changes = changes.filter(bigcommerce_product=product)
    else:
        changes = changes.filter(hidden=show_hidden)

    category = request.GET.get('category')
    if category:
        changes = changes.filter(categories__icontains=category)
    product_type = request.GET.get('product_type', '')
    if product_type:
        changes = changes.filter(bigcommerce_product__product_type__icontains=product_type)

    changes = changes.order_by('-updated_at')

    paginator = SimplePaginator(changes, post_per_page)
    page = min(max(1, page), paginator.num_pages)
    page = paginator.page(page)
    changes = page.object_list

    products = []
    product_variants = {}
    for i in changes:
        bigcommerce_id = i.product.source_id
        if bigcommerce_id and str(bigcommerce_id) not in products:
            products.append(str(bigcommerce_id))
    try:
        if len(products):
            products = utils.get_bigcommerce_products(store=store, product_ids=products)
            for p in products:
                product_variants[str(p['id'])] = p
    except:
        raven_client.captureException()

    product_changes = []
    for i in changes:
        change = {'qelem': i}
        change['id'] = i.id
        change['data'] = i.get_data()
        change['changes'] = i.get_changes_map(category)
        change['product'] = i.product
        change['bigcommerce_link'] = i.product.bigcommerce_url
        change['original_link'] = i.product.get_original_info().get('url')
        p = product_variants.get(str(i.product.source_id), {})
        variants = p.get('variants', None)
        for c in change['changes']['variants']['quantity']:
            if variants is not None and len(variants) > 0:
                index = variant_index_from_supplier_sku(i.product, c['sku'], variants)
                if index is not None:
                    if p['inventory_tracking'] == 'variant':
                        c['bigcommerce_value'] = variants[index]['inventory_level']
                    else:
                        c['bigcommerce_value'] = "Unmanaged"
                else:
                    c['bigcommerce_value'] = "Not Found"
            elif len(variants) == 0:
                if p['inventory_tracking'] == 'product':
                    c['bigcommerce_value'] = p['inventory_level']
                else:
                    c['bigcommerce_value'] = "Unmanaged"
            else:
                c['bigcommerce_value'] = "Not Found"
        for c in change['changes']['variants']['price']:
            if variants is not None and len(variants) > 0:
                index = variant_index_from_supplier_sku(i.product, c['sku'], variants)
                if index is not None:
                    c['bigcommerce_value'] = variants[index]['sale_price']
                else:
                    c['bigcommerce_value_label'] = "Not Found"
            elif len(variants) == 0:
                c['bigcommerce_value'] = p['sale_price']
            else:
                c['bigcommerce_value_label'] = "Not Found"

        product_changes.append(change)

    # Allow sending notification for new changes
    cache.delete('product_change_%d' % request.user.models_user.id)

    # Delete sidebar alert info cache
    cache.delete(make_template_fragment_key('alert_info', [request.user.id]))

    tpl = 'bigcommerce/product_alerts_tab.html' if request.GET.get('product') else 'bigcommerce/product_alerts.html'
    return render(request, tpl, {
        'product_changes': product_changes,
        'show_hidden': show_hidden,
        'product': product,
        'paginator': paginator,
        'current_page': page,
        'page': 'product_alerts',
        'store': store,
        'category': category,
        'product_type': product_type,
        'breadcrumbs': [{'title': 'Products', 'url': '/product'}, 'Alerts'],
        'selected_menu': 'products:alerts'
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
            store = BigCommerceStore.objects.get(id=request.GET.get('store'))
            permissions.user_can_view(request.user, store)

            product = BigCommerceProduct.objects.get(id=request.GET.get('product'))
            permissions.user_can_edit(request.user, product)

            api_product = product.sync()

            first_image = api_product['images'][0] if len(api_product['images']) else ''
            results = []
            if 'variants' in api_product:
                for v in api_product['variants']:
                    results.append({
                        'value': v['sku'],
                        'data': v['id'],
                        'image': v.get('image_url', first_image),
                    })

            if not len(results):
                results.append({
                    'value': "Default",
                    'data': api_product['id'],
                    'image': first_image
                })

            return JsonResponse({'query': q, 'suggestions': results}, safe=False)

        except BigCommerceStore.DoesNotExist:
            return JsonResponse({'error': 'Store not found'}, status=404)

        except BigCommerceProduct.DoesNotExist:
            return JsonResponse({'error': 'Product not found'}, status=404)

    elif target == 'types':
        types = []
        for product in request.user.models_user.bigcommerceproduct_set.only('product_type').filter(product_type__icontains=q).order_by()[:10]:
            if product.product_type not in types:
                types.append(product.product_type)

        return JsonResponse({'query': q, 'suggestions': [{'value': i, 'data': i} for i in types]}, safe=False)

    else:
        return JsonResponse({'error': 'Unknown target'})


class ProductsList(ListView):
    model = BigCommerceProduct
    template_name = 'bigcommerce/products_grid.html'
    context_object_name = 'products'

    paginator_class = SimplePaginator
    paginate_by = 25

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        if not request.user.can('bigcommerce.use'):
            raise permissions.PermissionDenied()

        return super(ProductsList, self).dispatch(request, *args, **kwargs)

    def get_queryset(self):
        return bigcommerce_products(self.request)

    def get_context_data(self, **kwargs):
        context = super(ProductsList, self).get_context_data(**kwargs)

        context['breadcrumbs'] = [{'title': 'Products', 'url': reverse('bigcommerce:products_list')}]
        context['selected_menu'] = 'products:all'

        if self.request.GET.get('store', 'n') == 'n':
            context['breadcrumbs'].append({'title': 'Non Connected', 'url': reverse('bigcommerce:products_list') + '?store=n'})
        elif self.request.GET.get('store', 'n') == 'c':
            context['breadcrumbs'].append({'title': 'Connected', 'url': reverse('bigcommerce:products_list') + '?store=c'})
        elif safe_int(self.request.GET.get('store')):
            store = BigCommerceStore.objects.get(id=self.request.GET.get('store'))
            permissions.user_can_view(self.request.user, store)

            context['store'] = store
            context['breadcrumbs'].append({'title': store.title, 'url': '{}?store={}'.format(reverse('bigcommerce:products_list'), store.id)})

        return context


class ProductDetailView(DetailView):
    model = BigCommerceProduct
    template_name = 'bigcommerce/product_detail.html'
    context_object_name = 'product'

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        if not request.user.can('bigcommerce.use'):
            raise permissions.PermissionDenied()

        return super(ProductDetailView, self).dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super(ProductDetailView, self).get_context_data(**kwargs)
        permissions.user_can_view(self.request.user, self.object)
        products = reverse('bigcommerce:products_list')

        if self.object.source_id:
            try:
                context['bigcommerce_product'] = self.object.sync()
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

        last_check = None
        try:
            if self.object.monitor_id > 0:
                cache_key = 'bigcommerce_product_last_check_{}'.format(self.object.id)
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

        context['token'] = jwt.encode({
            'id': self.request.user.id,
            'exp': arrow.utcnow().replace(hours=6).timestamp
        }, settings.API_SECRECT_KEY, algorithm='HS256')

        return context


class ProductMappingView(DetailView):
    model = BigCommerceProduct
    template_name = 'bigcommerce/product_mapping.html'
    context_object_name = 'product'

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        if not request.user.can('bigcommerce.use'):
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

    def get_variants_map(self, bigcommerce_product, product, supplier):
        variants_map = product.get_variant_mapping(supplier=supplier)
        variants_map = {key: json.loads(value) for key, value in list(variants_map.items())}
        for variant in bigcommerce_product.get('variants', []):
            attributes = variant.get('attributes', [])
            options = [{'title': option['option']} for option in attributes]
            variants_map.setdefault(str(variant['id']), options)

        return variants_map

    def get_context_data(self, **kwargs):
        context = super(ProductMappingView, self).get_context_data(**kwargs)
        product = self.object
        bigcommerce_product = product.sync()
        context['bigcommerce_product'] = bigcommerce_product
        context['product'] = product
        context['store'] = product.store
        context['product_id'] = product.id
        context['product_suppliers'] = self.get_product_suppliers(product)
        context['current_supplier'] = current_supplier = self.get_current_supplier(product)
        context['variants_map'] = self.get_variants_map(bigcommerce_product, product, current_supplier)
        context['selected_menu'] = 'products:all'

        return context


class MappingSupplierView(DetailView):
    model = BigCommerceProduct
    template_name = 'bigcommerce/mapping_supplier.html'
    context_object_name = 'product'

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        if not request.user.can('bigcommerce.use'):
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
        bigcommerce_product = product.sync()
        context['bigcommerce_product'] = bigcommerce_product
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
            {'title': 'Products', 'url': reverse('bigcommerce:products_list')},
            {'title': product.store.title, 'url': '{}?store={}'.format(reverse('bigcommerce:products_list'), product.store.id)},
            {'title': product.title, 'url': reverse('bigcommerce:product_detail', args=[product.id])},
            'Advanced Mapping'
        ]
        context['selected_menu'] = 'products:all'

        self.add_supplier_info(bigcommerce_product.get('variants', []), suppliers_map)

        return context


class MappingBundleView(DetailView):
    model = BigCommerceProduct
    template_name = 'bigcommerce/mapping_bundle.html'
    context_object_name = 'product'

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        if not request.user.can('bigcommerce.use'):
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
            {'title': 'Products', 'url': reverse('bigcommerce:products_list')},
            {'title': self.object.store.title, 'url': '{}?store={}'.format(reverse('bigcommerce:products_list'), self.object.store.id)},
            {'title': self.object.title, 'url': reverse('bigcommerce:product_detail', args=[self.object.id])},
            'Bundle Mapping'
        ]

        context.update({
            'store': product.store,
            'product_id': product.id,
            'product': product,
            'bundle_mapping': bundle_mapping,
            'selected_menu': 'products:all',
        })

        return context


class VariantsEditView(DetailView):
    model = BigCommerceProduct
    template_name = 'bigcommerce/variants_edit.html'
    slug_field = 'source_id'
    slug_url_kwarg = 'pid'

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        if not request.user.can('product_variant_setup.use'):
            return render(request, 'bigcommerce/upgrade.html')

        return super(VariantsEditView, self).dispatch(request, *args, **kwargs)

    def get_object(self, queryset=None):
        kwarg = {
            'source_id': self.kwargs['pid'],
            'store': self.get_store(),
        }

        try:
            product = BigCommerceProduct.objects.get(**kwarg)
        except BigCommerceProduct.MultipleObjectsReturned:
            product = BigCommerceProduct.objects.filter(**kwarg).first()

        permissions.user_can_view(self.request.user, product)

        return product

    def get_store(self):
        store = get_object_or_404(BigCommerceStore, pk=self.kwargs['store_id'])
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
            {'title': 'Products', 'url': reverse('bigcommerce:products_list')},
            'Edit Variants',
        ]

        return context


class OrdersList(ListView):
    model = None
    template_name = 'bigcommerce/orders_list.html'
    context_object_name = 'orders'
    paginator_class = BigCommerceListPaginator
    paginate_by = 20
    products = {}
    url = reverse_lazy('bigcommerce:orders_list')

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        if not request.user.can('bigcommerce.use'):
            raise permissions.PermissionDenied()

        if not self.get_store():
            messages.warning(request, 'Please add at least one store before using the Orders page.')
            return redirect('bigcommerce:index')

        if not request.user.can('place_orders.sub', self.get_store()):
            messages.warning(request, "You don't have access to this store orders")
            return redirect('bigcommerce:index')

        return super(OrdersList, self).dispatch(request, *args, **kwargs)

    def get_store(self):
        if not hasattr(self, 'store'):
            self.store = get_store_from_request(self.request)

        return self.store

    def get_filters(self):
        filters = {}
        params = self.request.GET

        if params.get('sort') in ['order_date', '!order_date']:
            filters['sort'] = 'date_created:asc'
            if params.get('sort') == 'order_date':
                filters['sort'] = 'date_created:asc'
            if params.get('sort') == '!order_date':
                filters['sort'] = 'date_created:desc'

        if params.get('status') and not params.get('status') == 'any':
            filters['status_id'] = params.get('status')

        if params.get('query'):
            filters['min_id'] = params.get('query')
            filters['max_id'] = params.get('query')

        return filters

    def get_queryset(self):
        return BigCommerceListQuery(self.get_store(), 'v2/orders', self.get_filters())

    def get_context_data(self, **kwargs):
        api_error = None

        context = {}

        try:
            context = super(OrdersList, self).get_context_data(**kwargs)
        except (requests.exceptions.HTTPError, requests.exceptions.ConnectionError) as e:
            api_error = f'HTTP Error: {http_excption_status_code(e)}'
        except:
            api_error = 'Store API Error'
            raven_client.captureException()

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
            raven_client.captureException()

        if api_error:
            messages.error(self.request, f'Error while trying to show your Store Orders: {api_error}')

        context['api_error'] = api_error

        return context

    def get_product_supplier(self, product, variant_id=None):
        if product.has_supplier():
            return product.get_supplier_for_variant(variant_id)

    def get_order_date_created(self, order):
        date_created = arrow.get(order['date_created'], 'ddd, D MMM YYYY HH:mm:ss Z')
        timezone = self.request.session.get('django_timezone')

        return date_created if not timezone else date_created.to(timezone)

    def get_order_date_paid(self, order):
        if order.get('date_created'):
            paid_date = arrow.get(order['date_created'], 'ddd, D MMM YYYY HH:mm:ss Z')
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
        aliexpress_fix_address = models_user.get_config('aliexpress_fix_address', True)
        aliexpress_fix_city = models_user.get_config('aliexpress_fix_city', True)
        german_umlauts = models_user.get_config('_use_german_umlauts', False)

        country = order['billing_address']['country_iso2']
        if len(order['shipping_addresses']) > 0:
            order['shipping_address'] = order['shipping_addresses'][0]
            country = order['shipping_addresses'][0]['country_iso2']

        _order, shipping_address = bigcommerce_customer_address(
            order=order,
            aliexpress_fix=aliexpress_fix_address and supplier and supplier.is_aliexpress,
            aliexpress_fix_city=aliexpress_fix_city,
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
            'total': safe_float(item['base_price'], 0.0),
            'store': store.id,
            'order': {
                'phone': {
                    'number': order['billing_address'].get('phone'),
                    'country': country,
                },
                'note': models_user.get_config('order_custom_note'),
                'epacket': bool(models_user.get_config('epacket_shipping')),
                'aliexpress_shipping_method': models_user.get_config('aliexpress_shipping_method'),
                'auto_mark': bool(models_user.get_config('auto_ordered_mark', True)),  # Auto mark as Ordered
            },
        }

    def get_order_data_variant(self, product, line):
        mapped = product.get_variant_mapping(name=line['variant_id'],
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
        for product in BigCommerceProduct.objects.filter(store=store, source_id__in=product_ids):
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
        for track in BigCommerceOrderTrack.objects.filter(store=store, order_id__in=order_ids):
            key = '{}_{}_{}'.format(track.order_id, track.line_id, track.product_id)
            track_by_item[key] = track

        return track_by_item

    def normalize_orders(self, context):
        orders_cache = {}
        store = self.get_store()
        admin_url = store.get_admin_url()
        orders = context.get('orders', [])
        for order in orders:
            order['line_items'] = get_order_product_data(store, order)
            order['shipping_addresses'] = get_order_shipping_addresses(store, order)
        product_ids = self.get_product_ids(orders)
        product_by_source_id = self.get_product_by_source_id(product_ids)
        product_data = self.get_product_data(product_ids)
        order_ids = self.get_order_ids(orders)
        order_track_by_item = self.get_order_track_by_item(order_ids)

        for order in orders:
            country_code = order['billing_address']['country_iso2']
            if len(order['shipping_addresses']) > 0:
                country_code = order['shipping_addresses'][0]['country_iso2']
            date_created = self.get_order_date_created(order)
            order['date_paid'] = self.get_order_date_paid(order)
            order['date'] = date_created.datetime
            order['date_str'] = date_created.format('MM/DD/YYYY')
            order['date_tooltip'] = date_created.format('YYYY/MM/DD HH:mm:ss')
            order['order_url'] = '{}/orders/{}/edit'.format(admin_url, order['id'])
            order['store'] = store
            order['placed_orders'] = 0
            order['connected_lines'] = 0
            order['tracked_lines'] = 0
            order['items'] = order.pop('line_items')
            order['lines_count'] = len(order['items'])
            order['has_shipping_address'] = len(order['shipping_addresses']) > 0

            for item in order.get('items'):
                self.update_placed_orders(order, item)
                product_id = item['product_id']
                product = product_by_source_id.get(product_id)
                data = product_data.get(product_id)
                item['product'] = product
                item['image'] = next(iter(data['images']), {}).get('url_standard') if data else None
                variant_id = item.get('variant_id')

                bundle_data = []
                if product:
                    bundles = product.get_bundle_mapping(variant_id)
                    if bundles:
                        product_bundles = []
                        for idx, b in enumerate(bundles):
                            b_product = BigCommerceProduct.objects.filter(id=b['id']).first()
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

                            product_bundles.append({
                                'product': b_product,
                                'supplier': b_supplier,
                                'shipping_method': b_shipping_method,
                                'quantity': b['quantity'] * item['quantity'],
                                'data': b
                            })

                            bundle_data.append({
                                'title': b_product.title,
                                'quantity': b['quantity'] * item['quantity'],
                                'product_id': b_product.id,
                                'source_id': b_supplier.get_source_id(),
                                'order_url': app_link('bigcommerce/orders/place', supplier=b_supplier.id, SABundle=True),
                                'variants': b_variants,
                                'shipping_method': b_shipping_method,
                                'country_code': country_code,
                                'supplier_type': b_supplier.supplier_type(),
                            })

                        item['bundles'] = product_bundles
                        item['is_bundle'] = len(bundle_data) > 0
                        order['have_bundle'] = True

                    if product.has_supplier():
                        supplier = self.get_product_supplier(product, variant_id)
                        order_data = self.get_order_data(order, item, product, supplier)
                        order_data['products'] = bundle_data
                        order_data['is_bundle'] = len(bundle_data) > 0
                        order_data['variant'] = self.get_order_data_variant(product, item)
                        order_data_id = order_data['id']
                        orders_cache['bigcommerce_order_{}'.format(order_data_id)] = order_data
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
    model = BigCommerceOrderTrack
    paginator_class = SimplePaginator
    template_name = 'bigcommerce/orders_track.html'
    context_object_name = 'orders'
    paginate_by = 20

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        if not request.user.can('bigcommerce.use'):
            raise permissions.PermissionDenied()

        if not self.get_store():
            messages.warning(request, 'Please add at least one store before using the Tracking page.')
            return redirect('bigcommerce:index')

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

        orders = BigCommerceOrderTrack.objects.select_related('store', 'user', 'user__profile') \
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
            orders = orders.filter(bigcommerce_status='fulfilled')
        elif fulfillment_filter == '0':
            orders = orders.exclude(bigcommerce_status='fulfilled')

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
            raven_client.captureException()

        if error:
            messages.error(self.request, f'Error while trying to show your Store Orders: {error}')

        context['api_error'] = error

        context['breadcrumbs'] = [{
            'title': 'Orders',
            'url': reverse('bigcommerce:orders_list')
        }, {
            'title': 'Tracking',
            'url': reverse('bigcommerce:orders_track')
        }, {
            'title': context['store'].title,
            'url': '{}?store={}'.format(reverse('bigcommerce:orders_list'), context['store'].id)
        }]
        context['selected_menu'] = 'orders:tracking'

        context['rejected_status'] = ALIEXPRESS_REJECTED_STATUS

        return context

    def get_store(self):
        if not hasattr(self, 'store'):
            self.store = get_store_from_request(self.request)

        return self.store


class BoardsList(ListView):
    model = BigCommerceBoard
    context_object_name = 'boards'
    template_name = 'bigcommerce/boards_list.html'

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
    model = BigCommerceBoard
    context_object_name = 'board'
    template_name = 'bigcommerce/board.html'

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

        products = bigcommerce_products(self.request, store=None, board=self.object.id)
        paginator = SimplePaginator(products, 25)
        page = safe_int(self.request.GET.get('page'), 1)
        page = paginator.page(page)

        context['searchable'] = True
        context['paginator'] = paginator
        context['products'] = page
        context['current_page'] = page
        context['breadcrumbs'] = [{'title': 'Boards', 'url': reverse('bigcommerce:boards_list')}, self.object.title]
        context['selected_menu'] = 'products:boards'

        return context


class OrderPlaceRedirectView(RedirectView):
    permanent = False
    query_string = False

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        if not request.user.can('bigcommerce.use'):
            raise permissions.PermissionDenied()

        return super(OrderPlaceRedirectView, self).dispatch(request, *args, **kwargs)

    def get_redirect_url(self, *args, **kwargs):
        product = None
        supplier = None

        if not self.request.GET.get('SAStore'):
            return set_url_query(self.request.get_full_path(), 'SAStore', 'bigcommerce')

        disable_affiliate = self.request.user.get_config('_disable_affiliate', False)

        if self.request.GET.get('nff'):
            disable_affiliate = True

        if self.request.GET.get('supplier'):
            supplier = BigCommerceSupplier.objects.get(id=self.request.GET['supplier'])
            permissions.user_can_view(self.request.user, supplier.product)

            product = supplier.short_product_url()

        elif self.request.GET.get('product'):
            product = self.request.GET['product']

            if safe_int(product):
                product = 'https://www.aliexpress.com/item//{}.html'.format(product)

        if not product:
            return Http404("Product or Order not set")

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

        redirect_url = affiliate_link_set_query(redirect_url, 'SAStore', 'bigcommerce')

        # Verify if the user didn't pass order limit
        parent_user = self.request.user.models_user
        plan = parent_user.profile.plan
        limit_check_key = 'order_limit_bigcommerce_{}'.format(parent_user.id)
        if cache.get(limit_check_key) is None and plan.auto_fulfill_limit != -1:
            month_start = [i.datetime for i in arrow.utcnow().span('month')][0]
            orders_count = parent_user.bigcommerceordertrack_set.filter(created_at__gte=month_start).count()

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

            order_data = order_data_cache(f'bigcommerce_{order_key}')
            prefix, store, order, line = order_key.split('_')

        if order_data:
            order_data['url'] = redirect_url
            caches['orders'].set(order_key, order_data, timeout=caches['orders'].ttl(order_key))

        if order_data and settings.KEEN_PROJECT_ID and not cache.get(event_key):
            try:
                store = BigCommerceStore.objects.get(id=store)
                permissions.user_can_view(self.request.user, store)
            except BigCommerceStore.DoesNotExist:
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
                'store_type': 'BigCommerce',
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
