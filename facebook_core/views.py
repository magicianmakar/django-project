import arrow
import json
import re
import requests
from datetime import datetime, timedelta
from requests.exceptions import HTTPError

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.cache import cache, caches
from django.db.models import Q
from django.forms.models import model_to_dict
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.generic import ListView
from django.views.generic.base import RedirectView
from django.views.generic.detail import DetailView

from addons_core.models import Addon
from leadgalaxy.utils import (
    affiliate_link_set_query,
    get_admitad_affiliate_url,
    get_admitad_credentials,
    get_aliexpress_affiliate_url,
    get_aliexpress_credentials,
    get_ebay_affiliate_url,
    set_url_query
)
from lib.exceptions import capture_exception, capture_message
from profits.mixins import ProfitDashboardMixin
from shopified_core import permissions
from shopified_core.decorators import PlatformPermissionRequired
from shopified_core.paginators import SimplePaginator
from shopified_core.shipping_helper import get_counrties_list
from shopified_core.tasks import keen_order_event
from shopified_core.utils import (
    ALIEXPRESS_REJECTED_STATUS,
    aws_s3_context,
    clean_query_id,
    format_queueable_orders,
    http_exception_response,
    http_excption_status_code,
    jwt_encode,
    order_data_cache,
    safe_float,
    safe_int
)
from suredone_core.utils import get_daterange_filters

from .models import FBBoard, FBOrderTrack, FBProduct, FBStore, FBSupplier
from .utils import FBListPaginator, FBOrderListQuery, FBUtils, get_store_from_request


class ProductsList(ListView):
    model = FBProduct
    template_name = 'facebook/products_grid.html'
    context_object_name = 'products'

    paginator_class = SimplePaginator
    paginate_by = 25

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        if not request.user.can('facebook.use'):
            raise permissions.PermissionDenied()

        return super(ProductsList, self).dispatch(request, *args, **kwargs)

    def get_queryset(self):
        store_id = self.request.GET.get('store', 'n')
        in_store = safe_int(self.request.GET.get('in'))
        sort = self.request.GET.get('sort')
        user = self.request.user

        try:
            return FBUtils(user).get_fb_products(store_id, in_store, sort=sort, request=self.request)
        except AttributeError:
            return []

    def get_context_data(self, **kwargs):
        context = super(ProductsList, self).get_context_data(**kwargs)
        context['breadcrumbs'] = [{'title': 'Products', 'url': reverse('fb:products_list')}]

        # Non-connected view
        if self.request.GET.get('store', 'n') == 'n':
            context['breadcrumbs'].append({'title': 'Non Connected', 'url': f"{reverse('fb:products_list')}?store=n"})

            in_store = safe_int(self.request.GET.get('in'))
            if in_store:
                in_store = get_object_or_404(FBStore, id=in_store, user=self.request.user.models_user)
                context['breadcrumbs'].append({'title': in_store.title,
                                               'url': f"{reverse('fb:products_list')}?store=n&in={in_store.id}"})
        # Connected view
        elif self.request.GET.get('store', 'n') == 'c':
            context['breadcrumbs'].append({'title': 'Connected', 'url': f"{reverse('fb:products_list')}?store=c"})

        # Connected to a specific fb store view
        elif safe_int(self.request.GET.get('store')):
            store = get_object_or_404(FBStore, id=self.request.GET.get('store'))
            permissions.user_can_view(self.request.user, store)

            context['store'] = store
            context['breadcrumbs'].append({'title': store.title,
                                           'url': f"{reverse('fb:products_list')}?store={store.id}"})

        context.update(aws_s3_context())
        context['token'] = jwt_encode({'id': self.request.user.id})
        return context


class ProductDetailView(DetailView):
    model = FBProduct
    template_name = 'facebook/product_detail.html'
    context_object_name = 'product'
    product_guid = ''
    store = None

    @method_decorator(login_required)
    def dispatch(self, request, pk, store_index, *args, **kwargs):
        if not request.user.can('facebook.use'):
            raise permissions.PermissionDenied()

        self.product_guid = pk
        self.store = get_object_or_404(FBStore, id=store_index)

        permissions.user_can_view(self.request.user, self.store)

        return super(ProductDetailView, self).dispatch(request, *args, **kwargs)

    def get_object(self, queryset=None):
        return FBUtils(self.request.user).get_fb_product_details(self.product_guid)

    def get_context_data(self, **kwargs):
        context = super(ProductDetailView, self).get_context_data(**kwargs)

        permissions.user_can_view(self.request.user, self.object)
        product_data_dict = model_to_dict(self.object)
        product_data_dict = {k: v for k, v in product_data_dict.items()
                             if k not in ['sd_updated_at', 'updated_at', 'created_at']}
        product_data_dict['status'] = context.get('product').parsed.get('status')

        context['product_data'] = json.dumps(product_data_dict, default=str)
        context['variants'] = json.dumps(self.object.variants_for_details_view)
        variants_config = self.object.parsed.get('variantsconfig', '{}')
        context['variants_config'] = json.loads(variants_config) if variants_config else []

        products_url = reverse('fb:products_list')
        context['breadcrumbs'] = [{'title': 'Products', 'url': products_url}, self.object.title]

        store_products = f'{products_url}?store={self.store.id}'
        context['breadcrumbs'].insert(1, {'title': self.store.title, 'url': store_products})

        return context


class ProductMappingView(DetailView):
    model = FBProduct
    template_name = 'facebook/product_mapping.html'
    context_object_name = 'product'
    product_guid = ''
    store = None

    @method_decorator(login_required)
    def dispatch(self, request, pk, store, *args, **kwargs):
        if not request.user.can('facebook.use'):
            raise permissions.PermissionDenied()

        self.product_guid = pk
        self.store = get_object_or_404(FBStore, id=store)

        return super(ProductMappingView, self).dispatch(request, *args, **kwargs)

    def get_object(self, queryset=None):
        try:
            product = FBProduct.objects.get(guid=self.product_guid)
            return product
        except FBProduct.DoesNotExist:
            return FBUtils(self.request.user).get_fb_product_details(self.product_guid)

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

    def get_current_supplier(self, product: FBProduct):
        pk = self.request.GET.get('supplier') or product.default_supplier_id
        return product.get_suppliers().get(pk=pk) if pk else None

    def get_variants_map(self, sd_product_data: dict, product: FBProduct, supplier: FBSupplier):
        variants_map = product.get_variant_mapping(supplier=supplier)
        variants_map = {key: json.loads(value) for key, value in list(variants_map.items())}
        if product.variants_config_parsed:
            var_attributes_keys = [i.get('title') for i in product.variants_config_parsed]
            for variant in product.product_variants.all():
                var_data = variant.parsed_variant_data
                options = [{'title': var_data.get(key)} for key in var_attributes_keys]
                variants_map.setdefault(variant.guid, options)

        return variants_map

    def get_context_data(self, **kwargs):
        context = super(ProductMappingView, self).get_context_data(**kwargs)
        product = self.object
        context['sd_product_data'] = sd_product_data = product.parsed
        context['product_suppliers'] = self.get_product_suppliers(product)
        context['current_supplier'] = current_supplier = self.get_current_supplier(product)
        context['variants_map'] = self.get_variants_map(sd_product_data, product, current_supplier)
        products_list_url = reverse('fb:products_list')
        context['breadcrumbs'] = [
            {'title': 'Products', 'url': products_list_url},
            {'title': product.store.title, 'url': f"{products_list_url}?store={self.store.id}"},
            {'title': product.title, 'url': reverse('fb:product_detail', args=[self.store.id, product.guid])},
            'Variants Mapping',
        ]

        return context


class MappingSupplierView(DetailView):
    model = FBProduct
    # template_name = 'facebook/mapping_supplier.html'
    context_object_name = 'product'
    product_guid = ''
    store = None


class MappingBundleView(DetailView):
    model = FBProduct
    # template_name = 'facebook/mapping_bundle.html'
    context_object_name = 'product'


class VariantsEditView(DetailView):
    model = FBProduct
    template_name = 'facebook/variants_edit.html'
    slug_field = 'source_id'
    slug_url_kwarg = 'pid'
    context_object_name = 'product'

    def get_context_data(self, **kwargs):
        product_data_dict = self.object.parsed
        sd_product_variants = list(product_data_dict.get('attributes', {}).values())
        sd_all_product_variants = [product_data_dict, *sd_product_variants]
        product_data_dict['variants'] = [{
            'id': index,
            'title': variant['varianttitle'],
            'guid': variant['guid']
        } for index, variant in enumerate(sd_all_product_variants)]

        # Collect all unique images of product
        all_images = []
        for variant in sd_all_product_variants:
            for i in range(10):
                i += 1
                if variant.get(f'media{i}'):
                    all_images.append(variant[f'media{i}'])
            if variant.get('mediax'):
                all_images += variant['mediax'].split('*')
        all_images = list(set(all_images))
        product_data_dict['images'] = [{'id': index, 'src': value} for index, value in enumerate(all_images)]

        product_url = reverse('fb:product_detail',
                              kwargs={'pk': self.object.guid, 'store_index': self.object.store.pk})
        context = {
            'store': self.object.store,
            'product_id': self.object.id,
            'product': product_data_dict,
            'is_connected': self.object.is_connected,
            'api_url': self.object.store.get_store_url(),
            'product_url': self.object.fb_url,
            'page': 'product',
            'breadcrumbs': [
                {'title': 'Products', 'url': reverse('fb:products_list')},
                {'title': 'Product Details', 'url': product_url},
                'Edit Variants'
            ]
        }

        return context


class OrdersList(ListView):
    model = None
    template_name = 'facebook/orders_list.html'
    context_object_name = 'orders'
    paginator_class = FBListPaginator
    _fb_utils = None
    paginate_by = 20
    products = {}
    url = reverse_lazy('fb:orders_list')
    bulk_queue = False
    store = None
    product_filter = None
    filters_config = {}

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        if not request.user.can('facebook.use'):
            raise permissions.PermissionDenied()

        if not self.get_store():
            messages.warning(request, 'Please add at least one store before using the Orders page.')
            return redirect('fb:index')

        if not request.user.can('place_orders.sub', self.get_store()):
            messages.warning(request, "You don't have access to this store orders")
            return redirect('fb:index')

        self.bulk_queue = bool(request.GET.get('bulk_queue'))
        if self.bulk_queue and not request.user.can('bulk_order.use'):
            return JsonResponse({'error': "Your plan doesn't have Bulk Ordering feature."}, status=402)

        return super(OrdersList, self).dispatch(request, *args, **kwargs)

    def get_store(self):
        if not hasattr(self, 'store') or not self.store:
            self.store = get_store_from_request(self.request)

        return self.store

    @property
    def fb_utils(self):
        if not hasattr(self, '_fb_utils') or not self._fb_utils:
            self._fb_utils = FBUtils(self.request.user)

        return self._fb_utils

    def render_to_response(self, context, **response_kwargs):
        if self.bulk_queue:
            return format_queueable_orders(context['orders'], context['page_obj'], store_type='fb', request=self.request)

        return super().render_to_response(context, **response_kwargs)

    def get_filters(self):
        """
        All possible filter values:
            orderby: 'dateutc' or 'dateupdatedutc' or 'total' or 'shippingcountry'
            order: 'desc' or 'asc'
            after: date in the ISO format
            before: date in the ISO format
            customer:
                first_name: string
                last_name: string
                email: email in a string type
            order_id: fb order in a string type
            product: TODO
            status: TODO
            supplier: TODO
        :return:
        :rtype:
        """
        filters = {}
        params = self.request.GET

        # Sort by
        params_sort = params.get('sort')
        if params_sort in ['dateutc', 'dateupdatedutc', 'total', 'shippingcountry']:
            filters['orderby'] = params_sort
        else:
            filters['orderby'] = 'dateutc'

        # Use the descending order by default so that the newest products are displayed first
        params_sort_order = params.get('desc', 'true') == 'true'
        filters['order'] = 'desc' if params_sort_order else 'asc'

        # Filtering by dates
        params_daterange = params.get('created_at_daterange')
        if params_daterange and not params_daterange == 'all':
            filters['after'], filters['before'] = get_daterange_filters(params_daterange)

        # Filtering by customer
        params_customer = {
            'first_name': params.get('query_customer_first_name'),
            'last_name': params.get('query_customer_last_name'),
            'email': params.get('query_customer_email')
        }
        if any(params_customer.values()):
            filters['customer'] = params_customer

        # Filtering by order ID
        params_order_id = params.get('query_order_id')
        if params_order_id:
            filters['order_id'] = params_order_id

        # Filtering by product
        product_guid = params.get('product')
        if product_guid:
            self.product_filter = self.fb_utils.get_fb_product_details(product_guid)
            filters['product'] = self.product_filter.source_id

        # Filtering by country
        params_country = params.get('query_country')
        if params_country:
            filters['country'] = params_country

        if params.get('status') and not params.get('status') == 'any':
            filters['status'] = params.get('status')

        return filters

    def get_queryset(self):
        self.filters_config = self.get_filters()
        self.filters_config['bulk_queue'] = self.bulk_queue

        today = datetime.today().strftime('%Y-%m-%dT%H:%M:%S.%f')
        thirty_days_ago = (datetime.today() - timedelta(days=30)).strftime('%Y-%m-%dT%H:%M:%S.%f')
        _, limit_date = self.fb_utils.get_orders_count_and_limit_date(self.request.user, thirty_days_ago, today)

        if (limit_date and not self.filters_config.get('before')
                or limit_date and self.filters_config['before'] > limit_date):
            self.filters_config['before'] = limit_date.replace(' ', 'T')
        return FBOrderListQuery(self.request.user, self.get_store(), self.filters_config)

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
        context['shipping_carriers'] = self.fb_utils.store_shipping_carriers()
        context['created_at_daterange'] = self.request.GET.get('created_at_daterange', '')
        context['product_filter'] = getattr(self, 'product_filter', None)
        context['filters_config'] = self.filters_config
        context['countries'] = get_counrties_list()
        context['use_extension_quick'] = self.request.user.models_user.can('aliexpress_extension_quick_order.use')

        # getting suredone order limit set in plan
        context['suredone_order_limit'] = self.request.user.profile.get_surdone_orders_limit()
        if context['suredone_order_limit'] > -1:
            today = datetime.today().strftime('%Y-%m-%dT%H:%M:%S.%f')
            thirty_days_ago = (datetime.today() - timedelta(days=30)).strftime('%Y-%m-%dT%H:%M:%S.%f')
            context['suredone_orders_count'], limit_date = self.fb_utils.get_orders_count_and_limit_date(
                self.request.user, thirty_days_ago, today)

        try:
            if context['suredone_order_limit'] == 0:
                context['suredone_orders_limit_usage_percent'] = 1
            else:
                context['suredone_orders_limit_usage_percent'] = safe_float(
                    context['suredone_orders_count']) / safe_float(context['suredone_order_limit'])
        except:
            context['suredone_orders_limit_usage_percent'] = 0
        if context['suredone_orders_limit_usage_percent'] > 0.8:
            context['suredone_orders_addons'] = Addon.objects.filter(suredone_orders_limit__gt=0, is_active=True).all()

        context['breadcrumbs'] = [
            {'title': 'Orders', 'url': self.url},
            {'title': store.title, 'url': f'{self.url}?store={store.id}'}]

        if api_error:
            messages.error(self.request, f'Error while trying to show your Store Orders: {api_error}')

        admitad_site_id, user_admitad_credentials = get_admitad_credentials(self.request.user.models_user)
        context['admitad_site_id'] = admitad_site_id if user_admitad_credentials else False

        context['api_error'] = api_error

        return context


class OrdersTrackList(ListView):
    model = FBOrderTrack
    paginator_class = SimplePaginator
    template_name = 'facebook/orders_track.html'
    context_object_name = 'orders'
    paginate_by = 20
    _fb_utils = None

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        if not request.user.can('facebook.use'):
            raise permissions.PermissionDenied()

        if not self.get_store():
            messages.warning(request, 'Please add at least one store before using the Tracking page.')
            return redirect('fb:index')

        return super(OrdersTrackList, self).dispatch(request, *args, **kwargs)

    @property
    def fb_utils(self):
        if not hasattr(self, '_fb_utils') or not self._fb_utils:
            self._fb_utils = FBUtils(self.request.user)

        return self._fb_utils

    def get_paginate_by(self, queryset):
        custom_limit = safe_int(self.request.user.get_config('_fb_order_track_limit'), None)
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

        orders = FBOrderTrack.objects.select_related('store', 'user', 'user__profile') \
            .filter(user=self.request.user.models_user, store=store) \
            .defer('data')
        if query:
            clean_query = clean_query_id(query)
            order_ids = self.fb_utils.order_id_from_name(store, query, [clean_query])

            orders = orders.filter(Q(order_id__in=order_ids)
                                   | Q(source_id=clean_query)
                                   | Q(source_tracking__icontains=query))

        if tracking_filter == '0':
            orders = orders.filter(source_tracking='')
        elif tracking_filter == '1':
            orders = orders.exclude(source_tracking='')

        if fulfillment_filter == '1':
            orders = orders.filter(fb_status='fulfilled')
        elif fulfillment_filter == '0':
            orders = orders.exclude(fb_status='fulfilled')

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
            context['orders'] = self.fb_utils.get_tracking_orders(context['orders'], self.paginate_by)

            try:
                context['orders'] = self.fb_utils.get_tracking_products(context['orders'], self.paginate_by)
            except Exception as e:
                capture_exception(extra=http_exception_response(e))

            context['shipping_carriers'] = self.fb_utils.store_shipping_carriers()

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
            'url': reverse('fb:orders_list')
        }, {
            'title': 'Tracking',
            'url': reverse('fb:orders_track')
        }, {
            'title': context['store'].title,
            'url': f"{reverse('fb:orders_list')}?store={context['store'].id}"
        }]

        context['rejected_status'] = ALIEXPRESS_REJECTED_STATUS

        return context

    def get_store(self):
        if not hasattr(self, 'store'):
            self.store = get_store_from_request(self.request)

        return self.store


class BoardsList(ListView):
    model = FBBoard
    context_object_name = 'boards'
    template_name = 'facebook/boards_list.html'

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
        context['breadcrumbs'] = ['Boards']

        return context


class BoardDetailView(DetailView):
    model = FBBoard
    context_object_name = 'board'
    template_name = 'facebook/board.html'

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

        products = FBUtils(self.request.user).get_fb_products(store_id=self.request.GET.get('store'),
                                                              in_store=self.request.GET.get('in'),
                                                              board=self.object.id)
        paginator = SimplePaginator(products, 25)
        page = safe_int(self.request.GET.get('page'), 1)
        page = paginator.page(page)

        context['searchable'] = True
        context['paginator'] = paginator
        context['products'] = page
        context['current_page'] = page
        context['breadcrumbs'] = [{'title': 'Boards', 'url': reverse('fb:boards_list')}, self.object.title]

        return context


class OrderPlaceRedirectView(RedirectView):
    permanent = False
    query_string = False

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        if not request.user.can('facebook.use'):
            raise permissions.PermissionDenied()

        return super(OrderPlaceRedirectView, self).dispatch(request, *args, **kwargs)

    def get_redirect_url(self, *args, **kwargs):
        if not self.request.user.can('auto_order.use'):
            messages.error(self.request, 'Your plan does not allow auto-ordering.')
            return '/fb/orders'

        if not self.request.GET.get('SAStore'):
            return set_url_query(self.request.get_full_path(), 'SAStore', 'fb')

        product = None
        supplier = None
        disable_affiliate = self.request.user.get_config('_disable_affiliate', False)

        if self.request.GET.get('nff'):
            disable_affiliate = True

        if self.request.GET.get('supplier'):
            supplier = get_object_or_404(FBSupplier, id=self.request.GET['supplier'])
            permissions.user_can_view(self.request.user, supplier.product)

            product = supplier.short_product_url()

        elif self.request.GET.get('product'):
            product = self.request.GET['product']

            if safe_int(product):
                product = f'https://www.aliexpress.com/item/{product}.html'

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
                    messages.error(self.request, 'eBay 1-Click fulfillment is not available on your current plan. '
                                                 'Please upgrade to Premier Plan to use this feature')

                    return '/'

                redirect_url = get_ebay_affiliate_url(product)
            else:
                if service == 'ali' and ali_api_key and ali_tracking_id:
                    redirect_url = get_aliexpress_affiliate_url(ali_api_key, ali_tracking_id, product)

                elif service == 'admitad':
                    redirect_url = get_admitad_affiliate_url(admitad_site_id, product)

        if not redirect_url:
            redirect_url = product

        for k in list(self.request.GET.keys()):
            if k.startswith('SA') and k not in redirect_url and self.request.GET[k]:
                redirect_url = affiliate_link_set_query(redirect_url, k, self.request.GET[k])

        redirect_url = affiliate_link_set_query(redirect_url, 'SAStore', 'fb')

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
        limit_check_key = f'order_limit_fb_{parent_user.id}'
        if cache.get(limit_check_key) is None and plan.auto_fulfill_limit != -1:
            month_start = [i.datetime for i in arrow.utcnow().span('month')][0]
            orders_count = parent_user.fbordertrack_set.filter(created_at__gte=month_start).count()

            if not settings.DEBUG and not plan.auto_fulfill_limit or orders_count + 1 > plan.auto_fulfill_limit:
                messages.error(self.request, 'You have reached your plan auto fulfill limit')
                return '/'

            cache.set(limit_check_key, arrow.utcnow().timestamp, timeout=3600)

        # Save Auto fulfill event
        event_data = {}
        order_data = None
        order_key = self.request.GET.get('SAPlaceOrder')
        event_key = None
        store = None
        if order_key:
            event_key = f"keen_event_{self.request.GET['SAPlaceOrder']}"

            if not order_key.startswith('order_'):
                order_key = f'order_{order_key}'

            order_data = order_data_cache(f'fb_{order_key}')
            prefix, store, order, line = order_key.split('_')

        if self.request.user.get_config('extension_version') == '3.41.0':
            # Fix for ePacket selection issue
            shipping_method = self.request.user.models_user.get_config('aliexpress_shipping_method')
            if supplier and supplier.is_aliexpress and 'SACompany' not in self.request.GET and shipping_method and shipping_method != 'EMS_ZX_ZX_US':
                return f"{re.sub(r'&$', '', self.request.get_full_path())}&SACompany={shipping_method}"

        if order_data:
            order_data['url'] = redirect_url
            caches['orders'].set(order_key, order_data, timeout=caches['orders'].ttl(order_key))

        if order_data and settings.KEEN_PROJECT_ID and not cache.get(event_key):
            try:
                store = FBStore.objects.get(id=store)
                permissions.user_can_view(self.request.user, store)
            except FBStore.DoesNotExist:
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
                'store_type': 'fb',
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
@method_decorator(PlatformPermissionRequired('facebook'), name='dispatch')
class ProfitDashboardView(ProfitDashboardMixin, ListView):
    store_type = 'fb'
    store_model = FBStore
    base_template = 'base_fb_core.html'


class AuthAcceptRedirectView(RedirectView):
    permanent = False
    query_string = False

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        if not request.user.can('facebook.use'):
            raise permissions.PermissionDenied()

        return super(AuthAcceptRedirectView, self).dispatch(request, *args, **kwargs)

    def get_redirect_url(self, *args, **kwargs):
        user = self.request.user
        instance_id = kwargs.get('store_index', 0) or 0

        error = self.request.GET.get('error')
        if error:
            error_reason = self.request.GET.get('error_reason')
            if error_reason == 'user_denied':
                messages.error(self.request, 'Failed to add a Facebook store. Please grant all required permissions '
                                             'to manage a store using Dropified.')
            else:
                messages.error(self.request, 'Failed to add a Facebook store. Please try again later.')

            capture_message('Error adding a Facebook store.', extra={
                'error': error,
                'error_code': self.request.GET.get('error_code'),
                'error_description': self.request.GET.get('error_description'),
                'error_reason': error_reason,
            })

            return reverse('fb:index')

        fb_code = self.request.GET.get('code')
        fb_granted_scopes = self.request.GET.get('granted_scopes')
        fb_denied_scopes = self.request.GET.get('denied_scopes')
        fb_state = self.request.GET.get('state')

        fb_utils = FBUtils(user)
        sd_api_resp = None
        try:
            sd_api_resp = fb_utils.api.authorize_fb_complete(
                instance=instance_id,
                code=fb_code,
                granted_scopes=fb_granted_scopes,
                denied_scopes=fb_denied_scopes,
                state=fb_state
            )
            sd_api_resp.raise_for_status()
        except HTTPError:
            capture_exception(extra={
                'description': 'API error when authorizing a Facebook store with SureDone.',
                'suredone_account_id': fb_utils.sd_account.id,
                'response_code': sd_api_resp.status_code if sd_api_resp else None,
                'response_reason': sd_api_resp.reason if sd_api_resp else None,
            })
            messages.error(self.request, 'Something went wrong when authorizing a Facebook store. Please try again.')
            return reverse('fb:index')

        resp_body = sd_api_resp.json()

        results = resp_body.get('results', {})
        successful_results = results.get('successful')

        if not successful_results:
            failed_results = results.get('failed')
            error_messages = []

            if isinstance(failed_results, dict):
                error_messages = [x.get('message') for x in failed_results.values() if x.get('message')]

            error_message_default = 'Failed to authorize a Facebook store. ' \
                                    'Please try again or report to support@dropified.com'
            error = '\n'.join(error_messages) if error_messages else error_message_default
            messages.error(self.request, error)
            return reverse('fb:index')

        instance_id_for_db = instance_id if instance_id != 0 else 1
        try:
            store = FBStore.objects.get(store_instance_id=instance_id_for_db, user=user.models_user)
        except FBStore.DoesNotExist:
            store = FBStore.objects.create(
                sd_account=fb_utils.sd_account,
                store_instance_id=instance_id_for_db,
                user=user.models_user,
                is_active=True,
            )

        messages.success(self.request, 'Your Facebook account has been added! '
                                       'Please complete the onboarding process below to complete authorization.')
        return reverse('fb:onboard', kwargs={'pk': store.id})


class CompleteAuthView(DetailView):
    model = FBStore
    context_object_name = 'store'
    template_name = 'facebook/shop_onboarding.html'

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        if not request.user.can('facebook.use'):
            raise permissions.PermissionDenied()

        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        permissions.user_can_view(self.request.user, self.object)
        context['breadcrumbs'] = ['Facebook Shop Onboarding']

        if self.object.auth_completed:
            error = f'The Facebook Store <strong>{self.object.title}</strong> has already been onboarded.'
            messages.error(self.request, error)
            return context

        fb_utils = FBUtils(self.request.user)
        try:
            context['fb_shops'] = fb_utils.get_fb_shop_options(self.object.filter_instance_id)
            if len(context['fb_shops']) == 0:
                error = 'No stores to onboard. Please make sure your Facebook account has permissions ' \
                        'to view your Facebook shop.'
                messages.error(self.request, error)
        except HTTPError:
            error = 'Failed to load Facebook commerce managers. Please try again later.'
            messages.error(self.request, error)

        return context


class ProductsImportView(ListView):
    model = None
    store = None
    template_name = 'facebook/products_import.html'
    context_object_name = 'products'
    _fb_utils = None

    @method_decorator(login_required)
    def dispatch(self, request, store, *args, **kwargs):
        if not request.user.can('fb.use'):
            raise permissions.PermissionDenied()

        self.store = get_object_or_404(FBStore, id=store)

        permissions.user_can_view(self.request.user, self.store)

        return super().dispatch(request, *args, **kwargs)

    @property
    def fb_utils(self):
        if not hasattr(self, '_fb_utils') or not self._fb_utils:
            self._fb_utils = FBUtils(self.request.user)

        return self._fb_utils

    def get_queryset(self):
        return []

    def get_context_data(self, **kwargs):
        api_error = None
        context = {}

        try:
            context = super().get_context_data(**kwargs)
        except (requests.exceptions.HTTPError, requests.exceptions.ConnectionError) as e:
            api_error = f'HTTP Error: {http_excption_status_code(e)}'
        except:
            api_error = 'Store API Error'
            capture_exception()

        context['ppp'] = min(safe_int(self.request.GET.get('ppp'), 50), 100)
        context['items_per_page_list'] = [20, 50, 100]
        context['current_page'] = self.request.GET.get('page', '1')

        fb_products_url = reverse('fb:products_list')

        context['store'] = self.store
        context['breadcrumbs'] = [
            {'title': 'Products', 'url': fb_products_url},
            {'title': self.store.title, 'url': f'{fb_products_url}?store={self.store.id}'}]

        if api_error:
            messages.error(self.request, f'Error while trying to load your products for import: {api_error}')

        context['api_error'] = api_error

        return context
