import json

from django.contrib.auth.decorators import login_required
from django.contrib.contenttypes.models import ContentType
from django.core.serializers.json import DjangoJSONEncoder
from django.db.models import prefetch_related_objects
from django.forms import model_to_dict
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views.generic import ListView
from django.views.generic.detail import DetailView

from lib.exceptions import capture_exception
from profits.utils import get_stores
from shopified_core import permissions
from shopified_core.paginators import SimplePaginator
from shopified_core.utils import aws_s3_context, jwt_encode

from .models import MasterProduct, ProductTemplate
from .utils import get_child_link, master_products


@method_decorator(login_required, name='dispatch')
class ProductsList(ListView):
    model = MasterProduct
    template_name = 'multichannel_products/products_grid.html'
    context_object_name = 'products'
    paginator_class = SimplePaginator
    paginate_by = 25

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        if not request.user.can('multichannel.use'):
            raise permissions.PermissionDenied()

        return super(ProductsList, self).dispatch(request, *args, **kwargs)

    def get_queryset(self):
        return master_products(self.request)

    def get_context_data(self, **kwargs):
        products_path = f"{reverse('multichannel:products_list')}?store=p"
        context = super().get_context_data(**kwargs)
        context['breadcrumbs'] = [{'title': 'Products', 'url': products_path},
                                  {'title': 'Multi-Channel', 'url': products_path}]
        return context


@method_decorator(login_required, name='dispatch')
class ProductDetailView(DetailView):
    model = MasterProduct
    template_name = 'multichannel_products/product_detail.html'
    context_object_name = 'product'

    @method_decorator(login_required)
    def dispatch(self, request, pk, *args, **kwargs):
        if not request.user.can('multichannel.use'):
            raise permissions.PermissionDenied()

        return super(ProductDetailView, self).dispatch(request, *args, **kwargs)

    def get_object(self, *args, **kwargs):
        product = super().get_object(*args, **kwargs)
        permissions.user_can_view(self.request.user, product)
        prefetch_related_objects([product], 'shopifyproduct_set', 'wooproduct_set', 'commercehqproduct_set',
                                 'groovekartproduct_set', 'bigcommerceproduct_set', 'ebayproduct_set', 'fbproduct_set',
                                 'googleproduct_set')

        return product

    def get_context_data(self, **kwargs):
        products_path = f"{reverse('multichannel:products_list')}?store=p"
        context = super().get_context_data(**kwargs)
        context['product_data'] = model_to_dict(self.object)
        context['product_data']['images'] = json.loads(context['product_data'].get('images'))
        context['product_data']['variants'] = json.loads(context['product_data'].get('variants_config')).get('variants')
        context['product_data']['variants_info'] = json.loads(context['product_data'].get('variants_config')).get(
            'variants_info')

        context['breadcrumbs'] = [{'title': 'Products', 'url': products_path}, self.object.title]
        context['breadcrumbs'].insert(1, {'title': 'Multi-Channel', 'url': products_path})

        context.update(aws_s3_context())

        context['last_check'] = None
        context['alert_config'] = {}

        context['token'] = jwt_encode({'id': self.request.user.id})

        context['upsell_alerts'] = not self.request.user.can('price_changes.use')
        context['config'] = self.request.user.get_config()
        context['user_stores'] = self.request.user.profile.get_stores(self.request, do_sync=False)['all']

        context['connected_stores'] = []
        for store in context['user_stores']:
            if store.store_type == 'shopify':
                children = store.shopifyproduct_set.filter(master_product=self.object)
            else:
                children = store.products.filter(master_product=self.object)

            if children:
                child = children.first()

                if store.store_type == 'shopify':
                    store.product = child.id
                    store.external_link = child.shopify_link
                elif store.store_type in ['fb', 'ebay', 'google']:
                    store.product = child.guid
                    if store.store_type == 'fb':
                        store.external_link = child.fb_url
                        store.is_pending = child.is_pending
                    elif store.store_type == 'ebay':
                        store.external_link = child.ebay_url
                    elif store.store_type == 'google':
                        store.external_link = child.google_url
                        store.is_pending = child.is_pending
                else:
                    store.product = child.id
                    if store.store_type == 'woo':
                        store.external_link = child.woocommerce_url
                    elif store.store_type == 'gkart':
                        store.external_link = child.groovekart_url
                    elif store.store_type == 'chq':
                        store.external_link = child.commercehq_url
                    elif store.store_type == 'bigcommerce':
                        store.external_link = child.bigcommerce_url

                store.child_url = get_child_link(child)
                store.published = child.is_connected
                context['connected_stores'].append(store)

        return context


@method_decorator(login_required, name='dispatch')
class VariantsMappingView(DetailView):
    model = MasterProduct
    template_name = 'multichannel_products/variants_mapping.html'
    context_object_name = 'product'

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        if not request.user.can('multichannel.use'):
            raise permissions.PermissionDenied()

        return super(VariantsMappingView, self).dispatch(request, *args, **kwargs)

    def get_object(self, queryset=None):
        product = super(VariantsMappingView, self).get_object(queryset)
        permissions.user_can_view(self.request.user, product)

        return product

    def get_context_data(self, **kwargs):
        context = super(VariantsMappingView, self).get_context_data(**kwargs)
        product = self.object
        context['product'] = product
        context['user_stores'] = self.request.user.profile.get_stores(self.request, do_sync=False)['all']

        context['variants'] = product.get_variants_titles() or []
        context['suredone_channels'] = ['fb', 'ebay', 'google']

        context['connected_stores'] = []
        for store in context['user_stores']:
            if store.store_type == 'shopify':
                children = store.shopifyproduct_set.filter(master_product=self.object)
            else:
                children = store.products.filter(master_product=self.object)

            if children:
                child = children.first()
                store.product = child
                store.master_variants_map = child.get_master_variants_map()

                from multichannel_products_core.api import get_helper_class
                helper = get_helper_class(
                    store.store_type,
                    product_id=child.guid if store.store_type in ['fb', 'ebay', 'google'] else child.id)
                variants_data = helper.get_variants()

                context['connected_stores'].append(dict(
                    id=store.id,
                    type=store.store_type,
                    title=store.title,
                    product=child.guid if store.store_type in context['suredone_channels'] else child.id,
                    variants_map=child.get_master_variants_map(),
                    variants_data=variants_data
                ))

        products_path = f"{reverse('multichannel:products_list')}?store=p"
        context['breadcrumbs'] = [
            {'title': 'Products', 'url': products_path},
            {'title': 'Multi-Channel', 'url': products_path},
            {'title': product.title, 'url': reverse('multichannel:product_detail', args=[product.id])},
            'Variants Mapping',
        ]
        return context


def get_store_from_request(request):
    try:
        store_id = request.POST.get('store') or request.GET.get('store')
        store_type = request.POST.get('store_type') or request.GET.get('store_type')
        if store_id and store_type:
            return get_stores(request.user, store_type).get(id=store_id)
    except:
        capture_exception()
        return None


class TemplatesList(ListView):
    model = ProductTemplate
    context_object_name = 'templates'
    template_name = 'multichannel_products/templates_list.html'

    store = None
    store_content_type = None

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        if not request.user.can('multichannel.use'):
            raise permissions.PermissionDenied()

        return super(TemplatesList, self).dispatch(request, *args, **kwargs)

    def get_store(self):
        if not hasattr(self, 'store') or not self.store:
            self.store = get_store_from_request(self.request)
            self.store_content_type = ContentType.objects.get_for_model(self.store)
        return self.store

    def get_queryset(self):
        if not hasattr(self, 'store') or not self.store:
            self.get_store()
        qs = super(TemplatesList, self).get_queryset()
        qs = qs.filter(content_type=self.store_content_type, object_id=self.store.id)
        return qs

    def get_context_data(self, **kwargs):
        context = super(TemplatesList, self).get_context_data(**kwargs)
        context['store'] = self.get_store()

        context['title_and_description_templates'] = context['templates'].filter(type='title_and_description')
        context['pricing_templates'] = context['templates'].filter(type='pricing')
        context['templates_list'] = json.loads(json.dumps(list(context['templates'].values()), cls=DjangoJSONEncoder))
        return context
