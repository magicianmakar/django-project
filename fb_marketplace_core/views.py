import arrow
import json
import requests

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views.generic import ListView
from django.views.generic.detail import DetailView

from shopified_core import permissions
from shopified_core.paginators import SimplePaginator
from shopified_core.utils import aws_s3_context, http_excption_status_code, jwt_encode, safe_int, url_join

from .models import FBMarketplaceProduct, FBMarketplaceStore
from .utils import fb_marketplace_products


class ProductsList(ListView):
    model = FBMarketplaceProduct
    template_name = 'fb_marketplace/products_grid.html'
    context_object_name = 'products'

    paginator_class = SimplePaginator
    paginate_by = 25

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        if not request.user.can('fb_marketplace.use'):
            raise permissions.PermissionDenied()

        return super(ProductsList, self).dispatch(request, *args, **kwargs)

    def get_queryset(self):
        return fb_marketplace_products(self.request)

    def get_context_data(self, **kwargs):
        context = super(ProductsList, self).get_context_data(**kwargs)

        context['breadcrumbs'] = [{'title': 'Products', 'url': reverse('fb_marketplace:products_list')}]

        if self.request.GET.get('store', 'n') == 'n':
            context['breadcrumbs'].append(
                {'title': 'Non Connected', 'url': reverse('fb_marketplace:products_list') + '?store=n'})
        elif self.request.GET.get('store', 'n') == 'c':
            context['breadcrumbs'].append(
                {'title': 'Connected', 'url': reverse('fb_marketplace:products_list') + '?store=c'})
        elif safe_int(self.request.GET.get('store')):
            store = FBMarketplaceStore.objects.get(id=self.request.GET.get('store'))
            permissions.user_can_view(self.request.user, store)

            context['store'] = store
            context['breadcrumbs'].append(
                {'title': store.title, 'url': '{}?store={}'.format(reverse('fb_marketplace:products_list'), store.id)})

        return context


class ProductDetailView(DetailView):
    model = FBMarketplaceProduct
    template_name = 'fb_marketplace/product_detail.html'
    context_object_name = 'product'

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        if not request.user.can('fb_marketplace.use'):
            raise permissions.PermissionDenied()

        return super(ProductDetailView, self).dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super(ProductDetailView, self).get_context_data(**kwargs)
        permissions.user_can_view(self.request.user, self.object)
        products = reverse('fb_marketplace:products_list')

        if self.object.is_connected:
            try:
                context['fb_marketplace_product'] = self.object
            except (requests.exceptions.HTTPError, requests.exceptions.ConnectionError) as e:
                messages.warning(self.request,
                                 f'Product details was not synced with your store (HTTP Error: {http_excption_status_code(e)})')

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
                cache_key = 'fb_marketplace_product_last_check_{}'.format(self.object.id)
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
    model = FBMarketplaceProduct
    template_name = 'fb_marketplace/product_mapping.html'
    context_object_name = 'product'

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        if not request.user.can('fb_marketplace.use'):
            raise permissions.PermissionDenied()

        return super(ProductMappingView, self).dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super(ProductMappingView, self).get_context_data(**kwargs)

        product = self.object
        permissions.user_can_view(self.request.user, self.object)

        context['fb_marketplace_product'] = product.sync()

        images_map = {}
        for option in context['fb_marketplace_product']['options']:
            for thumb in option['thumbnails']:
                if thumb.get('image'):
                    images_map[thumb['value']] = thumb['image']['path']

        for idx, variant in enumerate(context['fb_marketplace_product']['variants']):
            for v in variant['variant']:
                if v in images_map:
                    context['fb_marketplace_product']['variants'][idx]['image'] = images_map[v]
                    continue

            if len(variant['images']):
                context['fb_marketplace_product']['variants'][idx]['image'] = variant['images'][0]

        current_supplier = self.request.GET.get('supplier')
        if not current_supplier and product.default_supplier:
            current_supplier = product.default_supplier.id

        current_supplier = product.get_suppliers().get(id=current_supplier)

        variants_map = product.get_variant_mapping(supplier=current_supplier)

        seen_variants = []

        for i, v in enumerate(context['fb_marketplace_product']['variants']):
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
            context['fb_marketplace_product']['variants'][i]['default'] = options
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
            {'title': 'Products', 'url': reverse('fb_marketplace:products_list')},
            {'title': self.object.store.title,
             'url': '{}?store={}'.format(reverse('fb_marketplace:products_list'), self.object.store.id)},
            {'title': self.object.title, 'url': reverse('fb_marketplace:product_detail', args=[self.object.id])},
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
