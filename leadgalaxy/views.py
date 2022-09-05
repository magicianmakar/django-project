import arrow
import csv
import hmac
import io
import re
import requests
import simplejson as json
import time
from hashlib import sha1
from munch import Munch
from urllib.parse import quote_plus, urlencode

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login
from django.contrib.auth import logout as user_logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.views import LoginView
from django.core.cache import cache, caches
from django.core.cache.utils import make_template_fragment_key
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.signing import Signer
from django.db.models import Count, F, Max, Q
from django.http import Http404, HttpResponse, HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.defaultfilters import truncatewords
from django.urls import reverse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.clickjacking import xframe_options_exempt, xframe_options_sameorigin
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from django.views.decorators.http import require_http_methods
from django.views.generic.base import TemplateView

from alibaba_core import utils as alibaba_utils
from analytic_events.models import RegistrationEvent
from bigcommerce_core.models import BigCommerceProduct, BigCommerceSupplier, BigCommerceUserUpload
from commercehq_core.models import CommerceHQOrderTrack, CommerceHQProduct, CommerceHQSupplier, CommerceHQUserUpload
from ebay_core.models import EbayProduct, EbaySupplier, EbayUserUpload
from facebook_core.models import FBProduct, FBSupplier, FBUserUpload
from google_core.models import GoogleProduct, GoogleSupplier, GoogleUserUpload
from gearbubble_core.models import GearBubbleProduct, GearBubbleSupplier, GearUserUpload
from groovekart_core.models import GrooveKartProduct, GrooveKartSupplier, GrooveKartUserUpload
from infinite_pagination.paginator import InfinitePaginator
from lib.exceptions import capture_exception
from phone_automation import billing_utils as billing
from phone_automation.utils import get_month_limit, get_month_totals, get_phonenumber_usage
from product_alerts.models import ProductChange
from product_alerts.utils import variant_index_from_supplier_sku
from shopified_core import permissions
from shopified_core.exceptions import ApiLoginException, ApiProcessException
from shopified_core.mixins import AuthenticationMixin
from shopified_core.mocks import get_mocked_alert_changes, get_mocked_bundle_variants, get_mocked_supplier_variants
from shopified_core.paginators import FakePaginator, SimplePaginator
from shopified_core.shipping_helper import aliexpress_country_code_map, country_from_code, get_counrties_list
from shopified_core.tasks import keen_order_event
from shopified_core.utils import (
    ALIEXPRESS_REJECTED_STATUS,
    app_link,
    aws_s3_context,
    base64_decode,
    base64_encode,
    clean_query_id,
    decode_params,
    encode_params,
    fix_order_data,
    format_queueable_orders,
    hash_list,
    hash_text,
    jwt_decode,
    jwt_encode,
    order_data_cache,
    page_rpm_counter,
    products_filter,
    safe_float,
    safe_int,
    safe_str,
    update_product_data_images,
    url_join,
    using_replica,
    version_compare
)
from aliexpress_core.models import AliexpressAccount
from shopify_orders import utils as shopify_orders_utils
from shopify_orders.models import ShopifyOrder, ShopifyOrderLog, ShopifyOrderShippingLine, ShopifyOrderVariant, ShopifySyncStatus
from stripe_subscription.invoices.pdf import draw_pdf
from stripe_subscription.models import CustomStripePlan
from stripe_subscription.stripe_api import stripe
from stripe_subscription.utils import get_stripe_invoice, get_stripe_invoice_list
from supplements.lib.shipstation import get_address as get_shipstation_address
from supplements.models import PLSOrder
from supplements.tasks import update_shipstation_address
from suredone_core.utils import SureDoneUtils
from woocommerce_core.models import WooProduct, WooSupplier, WooUserUpload

from . import tasks, utils
from .forms import EmailAuthenticationForm, EmailForm, RegisterForm
from .models import (
    AccountRegistration,
    AdminEvent,
    CaptchaCredit,
    CaptchaCreditPlan,
    ClippingMagic,
    ClippingMagicPlan,
    FeatureBundle,
    GroupPlan,
    PlanRegistration,
    ProductSupplier,
    ShopifyBoard,
    ShopifyOrderTrack,
    ShopifyProduct,
    ShopifyProductImage,
    ShopifyStore,
    UserBlackSampleTracking,
    UserUpload,
    UserProfile
)
from .paginator import ShopifyOrderPaginator
from .templatetags.template_helper import money_format
from addons_core.models import Addon


def get_product(request, filter_products, post_per_page=25, sort=None, store=None, board=None, load_boards=False):
    products = []
    page = safe_int(request.GET.get('page'), 1)
    models_user = request.user.models_user
    user = request.user
    user_stores = list(request.user.profile.get_shopify_stores(flat=True))
    res = ShopifyProduct.objects.select_related('store') \
                                .defer('variants_map', 'shipping_map', 'notes') \
                                .filter(user=models_user) \
                                .filter(Q(store__in=user_stores) | Q(store=None))
    if store:
        if store == 'c':  # connected
            res = res.exclude(shopify_id=0)
        elif store == 'n':  # non-connected
            res = res.filter(shopify_id=0)

            in_store = safe_int(request.GET.get('in'))
            if in_store:
                in_store = get_object_or_404(ShopifyStore, id=in_store)
                if len(user_stores) == 1:
                    res = res.filter(Q(store=in_store) | Q(store=None))
                else:
                    res = res.filter(store=in_store)

                permissions.user_can_view(user, in_store)
        else:
            store = get_object_or_404(ShopifyStore, id=safe_int(store))
            res = res.filter(shopify_id__gt=0, store=store)

            permissions.user_can_view(user, store)

    if board:
        res = res.filter(shopifyboard=board)
        permissions.user_can_view(user, get_object_or_404(ShopifyBoard, id=board))

    if filter_products:
        res = products_filter(res, request.GET)

    sort = sort if sort else '-date'
    if sort:
        if re.match(r'^-?(title|price|date)$', sort):
            sort_columns = [sort.replace('date', 'created_at')]

            if sort_columns[0].endswith('created_at'):
                sort_columns.append('store_id')

            res = res.order_by(*sort_columns)

    if request.GET.get('product_board') in ['added', 'not_added']:
        board_list = request.user.models_user.shopifyboard_set.all()
        if request.GET.get('product_board') == "added":
            res = res.filter(shopifyboard__in=board_list)
        elif request.GET.get('product_board') == "not_added":
            res = res.exclude(shopifyboard__in=board_list)

    paginator = InfinitePaginator(res, post_per_page)
    page = paginator.page(page)
    res = page

    for i in res:
        p = {
            'qelem': i,
            'id': i.id,
            'store': i.store,
            'shopify_url': i.shopify_link(),
            'created_at': i.created_at,
            'updated_at': i.updated_at,
            'product': json.loads(i.data),
        }

        try:
            p['source'] = i.get_original_info(url=p['product']['original_url'])['source']
        except:
            pass

        p['price'] = '%.02f' % safe_float(p['product'].get('price'))
        p['price'] = money_format(p['price'], i.store)

        price_range = p['product'].get('price_range')
        if price_range and type(price_range) is list and len(price_range) == 2:
            p['price_range'] = '{} - {}'.format(
                money_format(price_range[0], i.store),
                money_format(price_range[1], i.store)
            )

        if 'images' not in p['product'] or not p['product']['images']:
            p['product']['images'] = []

        p['images'] = p['product']['images']

        products.append(p)

    if load_boards and len(products):
        link_product_board(products, request.user.get_boards())

    return products, paginator, page


def link_product_board(products, boards):

    fetch_list = ['p%d-%s' % (i['id'], i['qelem'].updated_at) for i in products]

    for i in boards:
        fetch_list.append('b%d-%s' % (i.id, i.updated_at))

    fetch_key = 'link_product_board_%s' % hash_list(fetch_list)

    cached_boards = cache.get(fetch_key)
    if cached_boards is None:
        fetched = ShopifyProduct.objects.prefetch_related('shopifyboard_set') \
                                        .only('id') \
                                        .filter(id__in=[i['id'] for i in products])

        cached_boards = {}
        for i in fetched:
            board = i.shopifyboard_set.first()
            cached_boards[i.id] = {'title': board.title} if board else None

        cache.set(fetch_key, cached_boards, timeout=3600)

    for i, v in enumerate(products):
        products[i]['board'] = cached_boards.get(v['id'])

    return products


@login_required
def products_list(request, tpl='grid'):
    store = request.GET.get('store', 'n')

    args = {
        'request': request,
        'filter_products': (request.GET.get('f') == '1'),
        'post_per_page': min(safe_int(request.GET.get('ppp'), settings.ITEMS_PER_PAGE), 100),
        'sort': request.GET.get('sort'),
        'store': store,
        'load_boards': (tpl is None or tpl == 'grid'),
    }

    if args['filter_products'] and not request.user.can('product_filters.use'):
        return render(request, 'upgrade.html')

    try:
        assert not request.is_ajax(), 'AJAX Request Detected - Products List'
    except:
        capture_exception(level='warning')

    products, paginator, page = get_product(**args)

    if not tpl or tpl == 'grid':
        tpl = 'product.html'
    else:
        tpl = 'product_table.html'

    try:
        store = ShopifyStore.objects.get(id=safe_int(store))
    except:
        store = None

    if store:
        try:
            utils.sync_shopify_products(store, products)
        except:
            pass

    breadcrumbs = [{'title': 'Products', 'url': '/product'}]

    if request.GET.get('store', 'n') == 'n':
        breadcrumbs.append({'title': 'Non Connected', 'url': '/product?store=n'})
    elif request.GET.get('store', 'n') == 'c':
        breadcrumbs.append({'title': 'Connected', 'url': '/product?store=c'})

    in_store = safe_int(request.GET.get('in'))
    if in_store:
        in_store = get_object_or_404(request.user.profile.get_shopify_stores(), id=in_store)
    elif store:
        in_store = store

    if in_store:
        breadcrumbs.append({'title': in_store.title, 'url': '/product?store={}'.format(in_store.id)})

    return render(request, tpl, {
        'paginator': paginator,
        'current_page': page,
        'filter_products': args['filter_products'],
        'products': products,
        'store': store,
        'ebay_manual_affiliate_link': request.user.can('ebay_manual_affiliate_link.use'),
        'page': 'product',
        'breadcrumbs': breadcrumbs
    })


@login_required
def shopify_migration(request):
    if not request.user.can('product_filters.use'):
        return render(request, 'upgrade.html')

    store = utils.get_store_from_request(request)
    if not store:
        messages.warning(request, 'Please add at least one store before using the Migration page.')
        return HttpResponseRedirect('/')

    ppp = min(safe_int(request.GET.get('ppp'), 50), 100)
    page = request.GET.get('page', '1')

    if request.GET.get('reset') == '1':
        request.user.profile.del_config_values('_shopify_products_filter_', True)

    category = utils.get_shopify_products_filter(request, 'category', '')
    status = utils.get_shopify_products_filter(request, 'status', 'any')
    title = utils.get_shopify_products_filter(request, 'title', '')

    if status not in ['connected', 'not_connected', 'any']:
        status = 'any'

    breadcrumbs = [
        {'url': '/product', 'title': 'Products'},
        {'url': '/product?store={}'.format(store.id), 'title': store.title},
    ]

    return render(request, 'shopify_migration.html', {
        'store': store,
        'category': category,
        'status': status,
        'title': title,
        'user_filter': utils.get_shopify_products_filter(request),
        'items_per_page_list': [10, 50, 100],
        'page': 'shopify_migration',
        'breadcrumbs': breadcrumbs,
        'ppp': ppp,
        'current_page': page
    })


@login_required
def product_view(request, pid):
    if request.user.is_superuser:
        product = get_object_or_404(ShopifyProduct, id=pid)
        if product.user != request.user:
            messages.warning(request, 'Preview Mode: Other features (like Variant Mapping,'
                                      ' Product info Tab, etc) will not work. '
                                      '<a href="/hijack/{u.id}?next=/product/{p.id}">'
                                      'Login as {u.username}</a>'.format(u=product.user, p=product))
    else:
        product = get_object_or_404(ShopifyProduct, id=pid)
        permissions.user_can_view(request.user, product)

    if not product.store and (not request.user.is_subuser or request.user.models_user.id not in [14970]):  # Intercom 11917013063
        product.store = product.user.profile.get_shopify_stores().first()
        product.save()

    try:
        alert_config = json.loads(product.config)
    except:
        alert_config = {}

    try:
        board = ShopifyBoard.objects.filter(products=product)
    except ShopifyBoard.DoesNotExist:
        board = None

    shopify_product = None
    if product.shopify_id and product.store:
        shopify_product = utils.get_shopify_product(product.store, product.shopify_id)

        if shopify_product:
            shopify_product = utils.link_product_images(shopify_product)

            if arrow.get(shopify_product['updated_at']).datetime > product.updated_at or request.GET.get('sync'):
                tasks.update_shopify_product(
                    store_id=product.store.id,
                    shopify_id=product.shopify_id,
                    shopify_product=shopify_product,
                    product_id=product.id)

                product.refresh_from_db()

    last_check = None
    try:
        if product.monitor_id and product.monitor_id > 0:
            cache_key = 'product_last_check_{}'.format(product.id)
            last_check = cache.get(cache_key)

            if last_check is None:
                response = requests.get(
                    url=url_join(settings.PRICE_MONITOR_HOSTNAME, '/api/products/', product.monitor_id),
                    auth=(settings.PRICE_MONITOR_USERNAME, settings.PRICE_MONITOR_PASSWORD),
                    timeout=10,
                )

                last_check = arrow.get(response.json()['updated_at'])
                cache.set(cache_key, last_check, timeout=3600)
    except:
        pass

    p = {
        'qelem': product,
        'id': product.id,
        'store': product.store,
        'user': product.user,
        'created_at': product.created_at,
        'updated_at': product.updated_at,
        'product': product.parsed,
        'notes': product.notes,
        'alert_config': alert_config,
        'last_check': last_check,
    }

    if 'images' not in p['product'] or not p['product']['images']:
        p['product']['images'] = []

    p['price'] = '$%.02f' % safe_float(p['product'].get('price'))

    p['images'] = p['product']['images']
    p['original_url'] = p['product'].get('original_url')

    if p['original_url'] and len(p['original_url']):
        if 'aliexpress' in p['original_url'].lower():
            try:
                p['original_product_id'] = re.findall('([0-9]+).html', p['original_url'])[0]
                p['original_product_source'] = 'ALIEXPRESS'
            except:
                pass

    p['source'] = product.get_original_info()

    original = None
    try:
        original = json.loads(product.get_original_data())
    except:
        pass

    if shopify_product:
        p['shopify_url'] = product.store.get_link('/admin/products/{}'.format(product.shopify_id))
        p['variant_edit'] = '/product/variants/{}/{}'.format(product.store.id, product.shopify_id)

        p['product']['description'] = shopify_product['body_html']
        p['product']['vendor'] = shopify_product['vendor']
        p['product']['published'] = shopify_product['published_at'] is not None

    breadcrumbs = [{'title': 'Products', 'url': '/product'}]

    if product.store_id:
        breadcrumbs.append({'title': product.store.title, 'url': '/product?store={}'.format(product.store.id)})

    breadcrumbs.append(p['product']['title'])

    aws = aws_s3_context()

    token = jwt_encode({'id': request.user.id})

    original_images = []
    if product.parent_product is None:
        if original:
            original_images = original.get('images', [])
    else:
        try:
            parent_original_data = json.loads(product.parent_product.get_original_data())
            original_images = parent_original_data.get('images', [])
        except:
            pass

    try:
        extra_images = original.get('extra_images', []) + original_images
        extra_images = [i.strip() for i in extra_images]
    except:
        extra_images = []

    return render(request, 'product_view.html', {
        'product': p,
        'board': board,
        'original': original,
        'shopify_product': shopify_product,
        'extra_images': extra_images,
        'aws_available': aws['aws_available'],
        'aws_policy': aws['aws_policy'],
        'aws_signature': aws['aws_signature'],
        'page': 'product',
        'breadcrumbs': breadcrumbs,
        'token': token,
        'upsell_alerts': not request.user.can('price_changes.use'),
        'config': request.user.get_config(),
    })


@login_required
def variants_edit(request, store_id, pid):
    """
    pid: Shopify Product ID
    """

    if not request.user.can('product_variant_setup.use'):
        return render(request, 'upgrade.html')

    store = get_object_or_404(ShopifyStore, id=store_id)
    permissions.user_can_view(request.user, store)

    product = utils.get_shopify_product(store, pid)

    if not product:
        messages.error(request, 'Product not found in Shopify')
        return HttpResponseRedirect('/')

    return render(request, 'variants_edit.html', {
        'store': store,
        'product_id': pid,
        'product': product,
        'api_url': store.get_link(),
        'page': 'product',
        'breadcrumbs': [{'title': 'Products', 'url': '/product'}, 'Edit Variants']
    })


@login_required
def product_mapping(request, product_id):
    product = get_object_or_404(ShopifyProduct, id=product_id)
    permissions.user_can_edit(request.user, product)

    if not product.default_supplier:
        suppliers = product.get_suppliers()
        if len(suppliers):
            product.set_default_supplier(suppliers[0], commit=True)
        else:
            messages.error(request, 'You have to add at least one supplier before using Variants Mapping')
            return HttpResponseRedirect('/product/{}'.format(product.id))

    current_supplier = safe_int(request.GET.get('supplier'))
    if not current_supplier and product.default_supplier:
        current_supplier = product.default_supplier.id

    current_supplier = product.productsupplier_set.get(id=current_supplier)

    shopify_id = product.get_shopify_id()
    if not shopify_id:
        raise Http404("Product doesn't exists on Shopify Store.")

    shopify_product = utils.get_shopify_product(product.store, shopify_id)
    if not shopify_product:
        messages.error(request, 'Product not found in Shopify')
        return HttpResponseRedirect('/')

    images = {}
    variants_map = product.get_variant_mapping(supplier=current_supplier)
    shopify_variants = {}

    for i in shopify_product['images']:
        for var in i['variant_ids']:
            images[var] = i['src']

    seen_variants = []
    for i, v in enumerate(shopify_product['variants']):
        shopify_product['variants'][i]['image'] = images.get(v['id'])

        mapped = variants_map.get(str(v['id']))
        if mapped:
            options = mapped
        else:
            options = []
            if v.get('option1') and v.get('option1').lower() != 'default title':
                options.append(v.get('option1'))
            if v.get('option2'):
                options.append(v.get('option2'))
            if v.get('option3'):
                options.append(v.get('option3'))

            options = [{'title': a} for a in options]

        try:
            if type(options) not in [list, dict]:
                options = json.loads(options)

                if type(options) is int:
                    options = str(options)
        except:
            pass

        variants_map[str(v['id'])] = options
        shopify_variants[str(v['id'])] = v
        shopify_product['variants'][i]['default'] = options
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
            'source_id': i.source_id,
        }

    return render(request, 'product_mapping.html', {
        'store': product.store,
        'product_id': product_id,
        'product': product,
        'shopify_product': shopify_product,
        'shopify_variants': shopify_variants,
        'variants_map': variants_map,
        'product_suppliers': product_suppliers,
        'current_supplier': current_supplier,
        'page': 'product',
        'breadcrumbs': [
            {'title': 'Products', 'url': '/product'},
            {'title': product.store.title, 'url': '/product?store={}'.format(product.store.id)},
            {'title': product.title, 'url': '/product/{}'.format(product.id)},
            'Variants Mapping',
        ]
    })


@login_required
def mapping_supplier(request, product_id):
    product = get_object_or_404(ShopifyProduct, id=product_id)
    permissions.user_can_edit(request.user, product)

    shopify_id = product.get_shopify_id()
    if not shopify_id:
        raise Http404("Product doesn't exists on Shopify Store.")

    shopify_product = utils.get_shopify_product(product.store, shopify_id)
    if not shopify_product:
        messages.error(request, 'Product not found in Shopify')
        return HttpResponseRedirect('/')

    images = {}
    suppliers_map = product.get_suppliers_mapping()

    for i in shopify_product['images']:
        for var in i['variant_ids']:
            images[var] = i['src']

    if not product.default_supplier:
        suppliers = product.get_suppliers()
        if len(suppliers):
            product.set_default_supplier(suppliers[0], commit=True)
        else:
            messages.error(request, 'You have to add at least one supplier before using Variants Mapping')
            return HttpResponseRedirect('/product/{}'.format(product.id))

    default_supplier_id = product.default_supplier.id
    for i, v in enumerate(shopify_product['variants']):
        supplier = suppliers_map.get(str(v['id']), {'supplier': default_supplier_id, 'shipping': {}})
        suppliers_map[str(v['id'])] = supplier

        shopify_product['variants'][i]['image'] = images.get(v['id'])
        shopify_product['variants'][i]['supplier'] = supplier['supplier']
        shopify_product['variants'][i]['shipping'] = supplier['shipping']

    product_suppliers = {}
    for i in product.get_suppliers():
        product_suppliers[i.id] = {
            'id': i.id,
            'name': i.get_name(),
            'url': i.product_url,
            'source_id': i.source_id,
        }

    shipping_map = product.get_shipping_mapping()
    variants_map = product.get_all_variants_mapping()
    mapping_config = product.get_mapping_config()

    upsell = False
    if not request.user.can('suppliers_shipping_mapping.use'):
        upsell = True
        shipping_map, mapping_config, suppliers_map = get_mocked_supplier_variants(variants_map)
        shopify_product['variants'] = shopify_product['variants'][:5]

    return render(request, 'mapping_supplier.html', {
        'upsell': upsell,
        'store': product.store,
        'product_id': product_id,
        'product': product,
        'shopify_product': shopify_product,
        'suppliers_map': suppliers_map,
        'shipping_map': shipping_map,
        'variants_map': variants_map,
        'product_suppliers': product_suppliers,
        'mapping_config': mapping_config,
        'countries': get_counrties_list(),
        'page': 'product',
        'breadcrumbs': [
            {'title': 'Products', 'url': '/product'},
            {'title': product.store.title, 'url': '/product/?store={}'.format(product.store.id)},
            {'title': product.title, 'url': '/product/{}'.format(product.id)},
            'Advanced Mapping',
        ]
    })


@login_required
def mapping_bundle(request, product_id):
    product = get_object_or_404(ShopifyProduct, id=product_id)
    permissions.user_can_edit(request.user, product)

    if not product.default_supplier:
        suppliers = product.get_suppliers()
        if len(suppliers):
            product.set_default_supplier(suppliers[0], commit=True)
        else:
            messages.error(request, 'You have to add at least one supplier before using Variants Mapping')
            return HttpResponseRedirect('/product/{}'.format(product.id))

    shopify_id = product.get_shopify_id()
    if not shopify_id:
        raise Http404("Product doesn't exists on Shopify Store.")

    shopify_product = utils.get_shopify_product(product.store, shopify_id)
    if not shopify_product:
        messages.error(request, 'Product not found in Shopify')
        return HttpResponseRedirect('/')

    images = {}

    for i in shopify_product['images']:
        for var in i['variant_ids']:
            images[var] = i['src']

    bundle_mapping = []

    for i, v in enumerate(shopify_product['variants']):
        if images.get(v['id']):
            v['image'] = images.get(v['id'])
        elif shopify_product.get('image') and shopify_product.get('image').get('src'):
            v['image'] = shopify_product['image']['src']

        v['products'] = product.get_bundle_mapping(v['id'], default=[])

        bundle_mapping.append(v)

    upsell = False
    if not request.user.can('mapping_bundle.use'):
        upsell = True
        bundle_mapping = get_mocked_bundle_variants(product, bundle_mapping)

    return render(request, 'mapping_bundle.html', {
        'upsell': upsell,
        'store': product.store,
        'product_id': product_id,
        'product': product,
        'shopify_product': shopify_product,
        'bundle_mapping': bundle_mapping,
        'page': 'product',
        'breadcrumbs': [
            {'title': 'Products', 'url': '/product'},
            {'title': product.store.title, 'url': '/product?store={}'.format(product.store.id)},
            {'title': product.title, 'url': '/product/{}'.format(product.id)},
            'Bundle Mapping',
        ]
    })


@login_required
def bulk_edit(request, what):
    if not request.user.can('bulk_editing.use'):
        return render(request, 'upgrade.html')

    if what == 'saved':
        args = {
            'request': request,
            'filter_products': (request.GET.get('f') == '1'),
            'post_per_page': settings.ITEMS_PER_PAGE,
            'sort': request.GET.get('sort'),
            'store': 'n'
        }

        if args['filter_products'] and not request.user.can('product_filters.use'):
            return render(request, 'upgrade.html')

        products, paginator, page = get_product(**args)

        return render(request, 'bulk_edit.html', {
            'products': products,
            'paginator': paginator,
            'current_page': page,
            'filter_products': args['filter_products'],
            'page': 'bulk',
            'breadcrumbs': [{'title': 'Products', 'url': '/product'}, 'Bulk Edit', 'Saved']
        })

    elif what == 'connected':
        products = request.GET.get('products')
        if not products:
            raise Http404

        # collect shopify product ids per a store
        stores = {}
        product_ids = {}

        if request.GET.get('store'):  # bulk edit products from one store
            store = get_object_or_404(ShopifyStore, id=request.GET.get('store'))
            stores[str(store.id)] = store
            product_ids[str(store.id)] = products
        else:  # bulk edit products from multiple store
            products = ShopifyProduct.objects.select_related('store').filter(pk__in=products.split(','))
            for product in products:
                store = product.store
                stores[str(store.id)] = store
                if not product_ids.get(str(store.id)):
                    product_ids[str(store.id)] = []
                product_ids[str(store.id)].append(str(product.shopify_id))

        # get shopify products per a store
        products = []
        for store_id in list(stores.keys()):
            store = stores[store_id]
            permissions.user_can_view(request.user, store)
            store_products = utils.get_shopify_products(
                store=store,
                product_ids=product_ids[store_id],
                fields='id,title,product_type,image,variants,vendor,tags')
            for product in list(store_products):
                product['store'] = store_id
                products.append(product)

        stores = list(stores.values())

        breadcrumbs = [{'title': 'Products', 'url': '/product'}, 'Bulk Edit']
        if len(stores) == 1:
            breadcrumbs.append(stores[0].title)

        return render(request, 'bulk_edit_connected.html', {
            'products': products,
            'stores': stores,
            'page': 'bulk',
            'breadcrumbs': breadcrumbs
        })

    raise Http404


@login_required
def boards_list(request):
    if not request.user.can('view_product_boards.sub'):
        raise PermissionDenied()

    store = utils.get_store_from_request(request)
    if not store:
        if request.user.profile.get_stores_count():
            return HttpResponseRedirect(reverse('goto-page', kwargs={'url_name': 'boards_list'}))

    search_title = request.GET.get('search') or None
    user_boards_list = request.user.models_user.shopifyboard_set.all()
    if search_title is not None:
        user_boards_list = user_boards_list.filter(title__icontains=search_title)
    boards_count = len(user_boards_list)

    paginator = SimplePaginator(user_boards_list, 12)
    page = safe_int(request.GET.get('page'), 1)
    page = min(max(1, page), paginator.num_pages)
    current_page = paginator.page(page)

    for board in current_page.object_list:
        board.saved = board.saved_count(request=request)
        board.connected = board.connected_count(request=request)

    return render(request, 'boards_list.html', {
        'current_page': current_page,
        'count': boards_count,
        'paginator': paginator,
        'page': 'boards',
        'breadcrumbs': ['Boards']
    })


@login_required
def boards_view(request, board_id):
    if not request.user.can('view_product_boards.sub'):
        raise PermissionDenied()

    board = get_object_or_404(ShopifyBoard, id=board_id)
    permissions.user_can_view(request.user, board)

    args = {
        'request': request,
        'filter_products': (request.GET.get('f') == '1'),
        'post_per_page': settings.ITEMS_PER_PAGE,
        'sort': request.GET.get('sort'),
        'store': request.GET.get('store'),
        'board': board.id
    }

    products, paginator, page = get_product(**args)

    board = {
        'id': board.id,
        'title': board.title,
        'products': products
    }

    return render(request, 'boards.html', {
        'board': board,
        'paginator': paginator,
        'current_page': page,
        'searchable': True,
        'page': 'boards',
        'breadcrumbs': [{'title': 'Boards', 'url': reverse(boards_list)}, board['title']]
    })


@xframe_options_sameorigin
def get_shipping_info(request):
    request_url = request.GET.get('url')
    if request_url:
        request_url = utils.set_url_query(request_url, 'useLocalAddress', 'false')

        res = requests.get(
            url=request_url,
            headers={
                "referer": "https://shoppingcart.aliexpress.com/orders.htm?aeOrderFrom=main_shopcart",
            })

        response = HttpResponse(res.text, content_type='text/javascript;charset=utf-8')

        # Add Cache control to response header
        expire_days = 7
        response['Cache-Control'] = f'max-age={expire_days * 86400}'
        response['Expires'] = timezone.now() + timezone.timedelta(days=expire_days)

        return response

    item_id = request.GET.get('id')
    product = request.GET.get('product')
    supplier = request.GET.get('supplier')
    supplier_type = request.GET.get('type')

    country = request.GET.get('country', request.user.get_config('_shipping_country', 'US'))
    country_code = aliexpress_country_code_map(country)
    country_name = country_from_code(country)

    zip_code = request.GET.get('zip_code', '')

    if request.GET.get('selected'):
        request.user.set_config('_shipping_country', country)

    if not item_id and supplier:
        if request.GET.get('chq'):

            if int(supplier) == 0:
                product = CommerceHQProduct.objects.get(id=product)
                permissions.user_can_view(request.user, product)
                supplier = product.default_supplier
            else:
                supplier = CommerceHQSupplier.objects.get(id=supplier)

        elif request.GET.get('woo'):

            if int(supplier) == 0:
                product = WooProduct.objects.get(id=product)
                permissions.user_can_view(request.user, product)
                supplier = product.default_supplier
            else:
                supplier = WooSupplier.objects.get(id=supplier)

        elif request.GET.get('ebay'):

            if int(supplier) == 0:
                product = EbayProduct.objects.get(guid=product)
                permissions.user_can_view(request.user, product)
                supplier = product.default_supplier
            else:
                supplier = EbaySupplier.objects.get(id=supplier)

        elif request.GET.get('fb'):

            if int(supplier) == 0:
                product = FBProduct.objects.get(guid=product)
                permissions.user_can_view(request.user, product)
                supplier = product.default_supplier
            else:
                supplier = FBSupplier.objects.get(id=supplier)

        elif request.GET.get('google'):

            if int(supplier) == 0:
                product = GoogleProduct.objects.get(guid=product)
                permissions.user_can_view(request.user, product)
                supplier = product.default_supplier
            else:
                supplier = GoogleSupplier.objects.get(id=supplier)

        elif request.GET.get('gear'):

            if int(supplier) == 0:
                product = GearBubbleProduct.objects.get(id=product)
                permissions.user_can_view(request.user, product)
                supplier = product.default_supplier
            else:
                supplier = GearBubbleSupplier.objects.get(id=supplier)

        elif request.GET.get('gkart'):

            if int(supplier) == 0:
                product = GrooveKartProduct.objects.get(id=product)
                permissions.user_can_view(request.user, product)
                supplier = product.default_supplier
            else:
                supplier = GrooveKartSupplier.objects.get(id=supplier)

        elif request.GET.get('bigcommerce'):

            if int(supplier) == 0:
                product = BigCommerceProduct.objects.get(id=product)
                permissions.user_can_view(request.user, product)
                supplier = product.default_supplier
            else:
                supplier = BigCommerceSupplier.objects.get(id=supplier)

        else:

            if int(supplier) == 0:
                product = ShopifyProduct.objects.get(id=product)
                permissions.user_can_view(request.user, product)
                supplier = product.default_supplier
            else:
                supplier = ProductSupplier.objects.get(id=supplier)

        item_id = supplier.get_source_id()

        if hasattr(supplier, 'is_ebay') and supplier.is_ebay:
            supplier_type = 'ebay'
        elif supplier.is_alibaba:
            supplier_type = 'alibaba'
        else:
            supplier_type = 'aliexpress'

    try:
        if supplier_type == 'ebay':
            shippement_data = utils.ebay_shipping_info(item_id, country_name, zip_code)
        elif supplier_type == 'alibaba':
            shippement_data = alibaba_utils.alibaba_shipping_info(request.user.models_user.alibaba.first(), item_id, country_code)
        else:
            shippement_data = utils.aliexpress_shipping_info(item_id, country_code)

    except requests.Timeout:
        capture_exception()

        if request.GET.get('type') == 'json':
            return JsonResponse({'error': 'Aliexpress Server Timeout'}, status=501)
        else:
            return render(request, '500.html', status=500)

    if request.GET.get('type') == 'json':
        return JsonResponse(shippement_data, safe=False)

    if not request.user.is_authenticated:
        return HttpResponseRedirect('%s?%s' % (reverse('login'),
                                               urlencode({'next': request.get_full_path()})))

    if request.GET.get('chq'):
        product = get_object_or_404(CommerceHQProduct, id=request.GET.get('product'))
    elif request.GET.get('woo'):
        product = get_object_or_404(WooProduct, id=request.GET.get('product'))
    elif request.GET.get('gear'):
        product = get_object_or_404(GearBubbleProduct, id=request.GET.get('product'))
    elif request.GET.get('gkart'):
        product = get_object_or_404(GrooveKartProduct, id=request.GET.get('product'))
    elif request.GET.get('bigcommerce'):
        product = get_object_or_404(BigCommerceProduct, id=request.GET.get('product'))
    elif request.GET.get('ebay'):
        product = get_object_or_404(EbayProduct, guid=request.GET.get('product'))
    elif request.GET.get('fb'):
        product = get_object_or_404(FBProduct, guid=request.GET.get('product'))
    elif request.GET.get('google'):
        product = get_object_or_404(GoogleProduct, guid=request.GET.get('product'))
    else:
        product = get_object_or_404(ShopifyProduct, id=request.GET.get('product'))

    permissions.user_can_view(request.user, product)

    product_data = json.loads(product.data)

    if 'store' in product_data:
        store = product_data['store']
    else:
        store = None

    tpl = 'shippement_info.html'
    if request.GET.get('for') == 'order':
        tpl = 'shippement_info_order.html'
    return render(request, tpl, {
        'country_code': country_code,
        'country_name': country_from_code(country),
        'selected_country_code': country,
        'info': shippement_data,
        'store': store
    })


@login_required
def dropified_black_users(request):
    if not request.user.is_superuser and not request.user.is_staff:
        raise PermissionDenied()

    if request.method == 'POST' and 'file' in request.FILES:
        def decode_utf8(input_iterator):
            for letter in input_iterator:
                yield letter.decode('utf-8')

        error_message = None
        selected_sample = request.POST['selected-sample']
        new_sample = request.POST['new-sample']
        # send_user_notification = 'send-user-notification' in request.POST

        if not selected_sample and not new_sample:
            error_message = 'Sample name is not set'

        spamreader = None
        email_field = 'email'
        tracking_field = 'tracking_number'

        if request.FILES["file"].content_type != 'text/csv':
            error_message = 'Uploaded file is not a CSV file'
        else:
            spamreader = csv.DictReader(decode_utf8(request.FILES["file"]))
            try:
                email_field = [i for i in spamreader.fieldnames if 'email' in i.lower()].pop()
            except:
                error_message = 'Coud not find Email column in the upload CSV file'

            try:
                tracking_field = [i for i in spamreader.fieldnames if 'tracking' in i.lower()].pop()
            except:
                error_message = 'Coud not find Tracking Number column in the upload CSV file'

        if not error_message:
            new_count = 0
            not_found = []
            for row in spamreader:
                try:
                    if not row[email_field]:
                        continue

                    user = User.objects.get(email__iexact=row[email_field])

                    UserBlackSampleTracking.objects.update_or_create(
                        user=user,
                        name=selected_sample or new_sample,
                        defaults={
                            'tracking_number': row[tracking_field],
                            'tracking_url': f'https://t.17track.net/en#nums={row[tracking_field]}',
                        })

                    new_count += 1
                except User.DoesNotExist:
                    not_found.append(row[email_field])

            if not_found:
                messages.warning(request, f'Could not find {len(not_found)} users:<br>{"<br>".join(not_found)} not found')

            messages.success(request, f'Tracking number add to {new_count} users')

        else:
            messages.error(request, error_message)

    plans = GroupPlan.objects.filter(slug__contains='black')
    users = User.objects.filter(profile__plan__in=plans)

    if request.GET.get('have_address'):
        if request.GET.get('have_address') == 'no':
            users = users.filter(profile__address=None)
        else:
            users = users.exclude(profile__address=None)

    if request.GET.get('sample'):
        if request.GET.get('sample_sent') == 'no':
            users = users.exclude(samples__name=request.GET.get('sample'))
        else:
            users = users.filter(samples__name=request.GET.get('sample'))

    samples = set(UserBlackSampleTracking.objects.all().values_list('name', flat=True))

    return render(request, 'acp/dropified_black_users.html', {
        'plans': plans,
        'users': users,
        'samples': samples,
        'page': 'acp_dropified_black_users',
        'breadcrumbs': ['ACP', 'Dropified Black Users']
    })


def autocomplete(request, target):
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'User login required'})

    q = request.GET.get('query', '').strip()
    if not q:
        q = request.GET.get('term', '').strip()

    if not q:
        return JsonResponse({'query': q, 'suggestions': []}, safe=False)

    if target == 'types':
        types = []
        for product in request.user.models_user.shopifyproduct_set.only('product_type').filter(product_type__icontains=q).order_by()[:10]:
            if product.product_type not in types:
                types.append(product.product_type)

        return JsonResponse({'query': q, 'suggestions': [{'value': i, 'data': i} for i in types]}, safe=False)

    if target == 'vendor':
        suppliers = []
        for supplier in ProductSupplier.objects.filter(store__in=request.user.profile.get_shopify_stores(), supplier_name__icontains=q)[:10]:
            if supplier.supplier_name and supplier.supplier_name not in suppliers:
                suppliers.append(supplier.supplier_name)

        return JsonResponse({'query': q, 'suggestions': [{'value': i, 'data': i} for i in suppliers]}, safe=False)

    elif target == 'tags':
        tags = []
        for product in request.user.models_user.shopifyproduct_set.only('tags').filter(tags=q).order_by()[:10]:
            for i in product.tags.split(','):
                i = i.strip()
                if i and i not in tags:
                    if q.lower() in i.lower():
                        tags.append(i)

        if 'term' in request.GET:
            return JsonResponse(tags, safe=False)
        else:
            return JsonResponse({'query': q, 'suggestions': [{'value': j, 'data': j} for j in tags]}, safe=False)

    elif target == 'title':
        results = []
        products = request.user.models_user.shopifyproduct_set.only('id', 'title', 'data').filter(title__icontains=q, shopify_id__gt=0)
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

    elif target == 'supplier-name':
        try:
            store = ShopifyStore.objects.get(id=request.GET.get('store'))
            permissions.user_can_view(request.user, store)

        except ShopifyStore.DoesNotExist:
            return JsonResponse({'error': 'Store not found'}, status=404)

        except PermissionDenied:
            capture_exception()
            return JsonResponse({'error': 'Permission Denied'}, status=403)

        suppliers = ProductSupplier.objects.only('supplier_name') \
                                           .distinct('supplier_name') \
                                           .filter(store=store) \
                                           .filter(supplier_name__icontains=q)

        results = []
        for supplier in suppliers[:10]:
            results.append({'value': supplier.supplier_name})

        return JsonResponse({'query': q, 'suggestions': results}, safe=False)
    elif target == 'shipping-method-name':
        try:
            store = ShopifyStore.objects.get(id=request.GET.get('store'))
            permissions.user_can_view(request.user, store)

        except ShopifyStore.DoesNotExist:
            return JsonResponse({'error': 'Store not found'}, status=404)

        except PermissionDenied:
            capture_exception()
            return JsonResponse({'error': 'Permission Denied'}, status=403)

        shipping_methods = ShopifyOrderShippingLine.objects.only('title') \
                                                           .distinct('title') \
                                                           .filter(title__icontains=q) \
                                                           .filter(store=store)

        results = []
        for shipping_method in shipping_methods:
            results.append({'value': shipping_method.title})

        return JsonResponse({'query': q, 'suggestions': results}, safe=False)

    elif target == 'variants':
        try:
            store = ShopifyStore.objects.get(id=request.GET.get('store'))
            permissions.user_can_view(request.user, store)

            product = ShopifyProduct.objects.get(id=request.GET.get('product'))
            permissions.user_can_edit(request.user, product)

            shopify_product = utils.get_shopify_product(store, product.shopify_id, raise_for_status=True)

            images = {}
            for i in shopify_product['images']:
                for var in i['variant_ids']:
                    images[var] = i['src']

            for i, v in enumerate(shopify_product['variants']):
                if images.get(v['id']):
                    shopify_product['variants'][i]['image'] = images.get(v['id'])
                elif shopify_product.get('image') and shopify_product.get('image').get('src'):
                    shopify_product['variants'][i]['image'] = shopify_product['image']['src']

            results = []
            for v in shopify_product['variants']:
                results.append({
                    'value': v['title'],
                    'data': v['id'],
                    'image': v.get('image')
                })

            return JsonResponse({'query': q, 'suggestions': results}, safe=False)

        except ShopifyStore.DoesNotExist:
            return JsonResponse({'error': 'Store not found'}, status=404)

        except ShopifyProduct.DoesNotExist:
            return JsonResponse({'error': 'Product not found'}, status=404)

    elif target == 'shopify-customer':
        try:
            store = ShopifyStore.objects.get(id=request.GET.get('store'))
            permissions.user_can_view(request.user, store)

            rep = requests.get(url=store.api('customers/search'), params={'query': q})
            rep.raise_for_status()

            results = []
            for v in rep.json()['customers']:
                results.append({
                    'value': '{} {} ({})'.format(v['first_name'] or '', v['last_name'] or '', v['email']).strip(),
                    'data': v['id'],
                })

            return JsonResponse({'query': q, 'suggestions': results}, safe=False)

        except ShopifyStore.DoesNotExist:
            return JsonResponse({'error': 'Store not found'}, status=404)

    else:
        return JsonResponse({'error': 'Unknown target'})


@login_required
def upload_file_sign(request):
    if not request.user.can('image_uploader.use'):
        return JsonResponse({'error': 'You don\'t have access to this feature.'})

    object_name = quote_plus(request.GET.get('file_name'))
    mime_type = request.GET.get('file_type')

    if 'image' not in mime_type.lower():
        return JsonResponse({'error': 'None allowed file type'})

    expires = int(time.time() + 60 * 60 * 24)
    amz_headers = "x-amz-acl:public-read"

    string_to_sign = "PUT\n\n%s\n%d\n%s\n/%s/%s" % (mime_type, expires, amz_headers, settings.AWS_STORAGE_BUCKET_NAME, object_name)

    signature = base64_encode(hmac.new(settings.AWS_SECRET_ACCESS_KEY.encode(), string_to_sign.encode(), sha1).digest())
    signature = quote_plus(signature.strip())

    url = 'https://%s.s3.amazonaws.com/%s' % (settings.AWS_STORAGE_BUCKET_NAME, object_name)

    content = {
        'signed_request': '%s?AWSAccessKeyId=%s&Expires=%s&Signature=%s' % (url, settings.AWS_ACCESS_KEY_ID, expires, signature),
        'url': url,
    }

    return JsonResponse(content, safe=False)


@login_required
@ensure_csrf_cookie
def user_profile(request):
    bundles = request.user.profile.bundles.filter(hidden_from_user=False)

    profile = request.user.models_user.profile

    show_plod_plan = [0, 2]
    if profile.private_label or profile.dropified_private_label or profile.plan.private_label:
        show_plod_plan = [1, 2]

    if request.GET.get('__plod'):
        show_plod_plan = [request.GET['__plod']]

    if request.GET.get('__revision'):
        plan_filter = {'revision': request.GET['__revision'], 'hidden': False}
    elif settings.PLAN_REVISION:
        plan_filter = {'revision': settings.PLAN_REVISION, 'hidden': False}
    else:
        plan_filter = {'hidden': False}

    stripe_plans = GroupPlan.objects.filter(show_in_plod_app__in=show_plod_plan) \
                                    .filter(**plan_filter) \
                                    .filter(payment_gateway='stripe') \
                                    .exclude(payment_interval='yearly') \
                                    .annotate(num_permissions=Count('permissions')) \
                                    .order_by('monthly_price', 'num_permissions')

    stripe_plans_yearly = GroupPlan.objects.filter(show_in_plod_app__in=show_plod_plan) \
                                   .filter(**plan_filter) \
                                   .filter(payment_gateway='stripe') \
                                   .filter(payment_interval='yearly') \
                                   .annotate(num_permissions=Count('permissions')) \
                                   .order_by('monthly_price', 'num_permissions')

    shopify_plans = GroupPlan.objects.filter(show_in_plod_app__in=show_plod_plan) \
                                     .filter(**plan_filter) \
                                     .filter(payment_gateway='shopify') \
                                     .exclude(payment_interval='yearly') \
                                     .annotate(num_permissions=Count('permissions')) \
                                     .order_by('monthly_price', 'num_permissions')

    shopify_plans_yearly = GroupPlan.objects.filter(show_in_plod_app__in=show_plod_plan) \
                                            .filter(**plan_filter) \
                                            .filter(payment_gateway='shopify') \
                                            .filter(payment_interval='yearly') \
                                            .annotate(num_permissions=Count('permissions')) \
                                            .order_by('monthly_price', 'num_permissions')

    stripe_paused_plan = GroupPlan.objects.filter(slug='paused-plan').first()
    shopify_paused_plan = GroupPlan.objects.filter(slug='paused-plan-shopify').first()
    try:
        if profile.plan.is_plod:
            stripe_downgrade_plan = GroupPlan.objects.filter(slug='plus-monthly').first()
        else:
            stripe_downgrade_plan = GroupPlan.objects.filter(slug='retro-monthly').first()
    except:
        stripe_downgrade_plan = None
    if request.user.get_config('_enable_yearly_60dc_plan'):
        stripe_plans_yearly = list(stripe_plans_yearly)
        stripe_plans_yearly.append(GroupPlan.objects.get(slug='premier-yearly-60dc'))

    clippingmagic_plans = ClippingMagicPlan.objects.all()
    clippingmagic = None
    if not request.user.profile.plan.is_free:
        try:
            clippingmagic = ClippingMagic.objects.get(user=request.user)

        except ClippingMagic.DoesNotExist:
            clippingmagic = ClippingMagic.objects.create(user=request.user, remaining_credits=5)

    captchacredit_plans = CaptchaCreditPlan.objects.all()
    captchacredit = None
    if not request.user.profile.plan.is_free:
        try:
            captchacredit = CaptchaCredit.objects.get(user=request.user)

        except CaptchaCredit.DoesNotExist:
            captchacredit = CaptchaCredit.objects.create(user=request.user, remaining_credits=0)
    stripe_customer = request.user.profile.plan.is_stripe() or request.user.profile.plan.is_free
    shopify_apps_customer = request.user.profile.from_shopify_app_store()

    # CallFlex Subscription context
    callflex = Munch({})

    callflex.month_limit_tollfree = get_month_limit(request.user, "tollfree")
    callflex.month_totals_tollfree = get_month_totals(request.user, "tollfree")
    if callflex.month_limit_tollfree:
        callflex.remaining_tollfree = callflex.month_limit_tollfree - callflex.month_totals_tollfree
    else:
        callflex.remaining_tollfree = False

    callflex.month_limit_local = get_month_limit(request.user, "local")
    callflex.month_totals_local = get_month_totals(request.user, "local")
    if callflex.month_limit_local:
        callflex.remaining_local = callflex.month_limit_local - callflex.month_totals_local
    else:
        callflex.remaining_local = False

    callflex.number_plans_monthly = CustomStripePlan.objects.filter(type="callflex_subscription", interval='month', hidden=False)
    callflex.number_plans_yearly = CustomStripePlan.objects.filter(type="callflex_subscription", interval='year', hidden=False)
    current_callflex_subscritption = request.user.customstripesubscription_set.filter(custom_plan__type='callflex_subscription').first()

    if current_callflex_subscritption:
        callflex.current_plan = current_callflex_subscritption.custom_plan
    else:
        callflex.current_plan = None

    shopify_admin_url = ''
    if shopify_apps_customer:
        # check existing recurring
        callflex.shopify_subscription = billing.get_shopify_recurring(request.user)
        shopify_store = request.user.models_user.profile.get_shopify_stores().first()
        if shopify_store is not None:
            shopify_admin_url = f'https://{shopify_store.get_shop(full_domain=True)}/admin/apps'

    callflex.phonenumber_usage_tollfree = get_phonenumber_usage(request.user, "tollfree")
    callflex.phonenumber_usage_local = get_phonenumber_usage(request.user, "local")

    callflex.extranumber_subscriptions = request.user.customstripesubscription_set.filter(custom_plan__type='callflex_subscription')

    stripe_customer_id = None
    if not request.user.is_subuser and stripe_customer:
        subscription = None
        while subscription is None:
            sub = request.user.stripesubscription_set.last()
            if sub is None:
                break

            try:
                sub.refresh()
                subscription = sub
            except stripe.error.InvalidRequestError:
                sub.delete()

        if subscription and settings.BAREMETRICS_ACCESS_TOKEN:
            stripe_customer_id = request.user.stripe_customer.customer_id

    if request.user.get_config('__plan'):
        free_plan = GroupPlan.objects.get(id=request.user.get_config('__plan'))
        if request.user.profile.plan != free_plan and request.user.profile.plan.free_plan:
            request.user.profile.change_plan(free_plan)

    return render(request, 'user/profile.html', {
        'countries': get_counrties_list(),
        'now': timezone.now(),
        'bundles': bundles,
        'stripe_plans': stripe_plans,
        'stripe_plans_yearly': stripe_plans_yearly,
        'stripe_paused_plan': stripe_paused_plan,
        'stripe_downgrade_plan': stripe_downgrade_plan,
        'shopify_paused_plan': shopify_paused_plan,
        'shopify_plans': shopify_plans,
        'shopify_plans_yearly': shopify_plans_yearly,
        'stripe_customer': stripe_customer,
        'baremetrics_form_enabled': bool(settings.BAREMETRICS_ACCESS_TOKEN),
        'stripe_customer_id': stripe_customer_id,
        'shopify_apps_customer': shopify_apps_customer,
        'clippingmagic_plans': clippingmagic_plans,
        'clippingmagic': clippingmagic,
        'captchacredit_plans': captchacredit_plans,
        'captchacredit': captchacredit,
        'example_dates': [arrow.utcnow().replace(days=-2).format('MM/DD/YYYY'), arrow.utcnow().replace(days=-2).humanize()],
        'callflex': callflex.toDict(),
        'shopify_admin_url': shopify_admin_url,
        'page': 'user_profile',
        'current_plan_revision': settings.PLAN_REVISION,
        'cancellation_coupon_applied': request.user.get_config('cancellation_coupon_applied'),
        'breadcrumbs': ['Profile']
    })


@login_required
def user_plan_change(request, hashed_str):

    try:
        plan_obj = GroupPlan.objects.get(register_hash=hashed_str)
    except GroupPlan.DoesNotExist:
        raise Http404('Invalid Plan')

    plan_id = plan_obj.id

    stripe_customer = request.user.profile.plan.is_stripe() or request.user.profile.plan.is_free
    if request.user.is_subuser or not stripe_customer or request.user.profile.plan.id == plan_id or \
            request.user.is_staff:
        raise PermissionDenied()

    return render(request, 'user/profile_plan_change.html', {
        'plan_id': plan_id,
        'title': plan_obj.title,
        'breadcrumbs': ['Plan Change']
    })


def user_unlock(request, token):
    data = cache.get('unlock_account_{}'.format(token))
    if data:
        username_hash = hash_text(data['username'].lower())

        cache.delete('login_attempts_{}'.format(username_hash))
        cache.delete('unlock_email_{}'.format(username_hash))
        cache.delete('unlock_account_{}'.format(token))

    messages.success(request, 'Your account has been unlocked')

    return HttpResponseRedirect('/')


@login_required
def upgrade_required(request):
    return render(request, 'upgrade.html')


def save_image_s3(request):
    """Saves the image in img_url into S3 with the name img_name"""
    request_token = request.GET.get('token')
    user = None
    if request_token:
        decoded_token = jwt_decode(request_token)

        user = User.objects.filter(pk=decoded_token.get('id')).first()  # Ensure None if doesn't exist
    elif request.user.is_authenticated:
        user = request.user

    if user is None:
        return HttpResponseRedirect(reverse('login'))

    if 'advanced' in request.GET:
        # PhotoPea
        if not user.can('pixlr_photo_editor.use'):
            return render(request, 'upgrade.html')

        if request.method == 'OPTIONS':
            response = HttpResponse()
            response["Access-Control-Allow-Origin"] = "https://www.photopea.com"
            response['Access-Control-Allow-Headers'] = 'Content-Type'
            return response

        fp = io.BytesIO(request.body)
        fp.read(2000)  # First 2000 bytes are json settings

        # TODO: File size limit
        product_id = request.GET.get('product')
        img_url = request.GET.get('url')
        old_url = request.GET.get('old_url')

    elif 'clippingmagic' in request.POST:
        if not user.can('clippingmagic.use'):
            return render(request, 'upgrade.html')

        product_id = request.POST.get('product')
        img_url = request.POST.get('url')
        old_url = request.POST.get('old_url')
        fp = io.BytesIO(requests.get(img_url, auth=(settings.CLIPPINGMAGIC_API_ID, settings.CLIPPINGMAGIC_API_SECRET)).content)
        img_url = '%s.png' % img_url

    else:
        # Aviary
        if not user.can('aviary_photo_editor.use'):
            return render(request, 'upgrade.html')

        product_id = request.POST.get('product')
        img_url = request.POST.get('url')
        old_url = request.POST.get('old_url')
        fp = request.FILES.get('image')

    upload_url = utils.upload_file_to_s3(img_url, user.id, fp=fp)

    if request.GET.get('chq') or request.POST.get('chq'):
        product = CommerceHQProduct.objects.get(id=product_id)
        permissions.user_can_edit(user, product)
        CommerceHQUserUpload.objects.create(user=user.models_user, product=product, url=upload_url[:510])

        if old_url and not old_url == upload_url:
            update_product_data_images(product, old_url, upload_url)

    elif request.GET.get('woo') or request.POST.get('woo'):
        product = WooProduct.objects.get(id=product_id)
        permissions.user_can_edit(user, product)

        WooUserUpload.objects.create(user=user.models_user, product=product, url=upload_url[:510])

        if old_url and not old_url == upload_url:
            update_product_data_images(product, old_url, upload_url)

    elif request.GET.get('gear') or request.POST.get('gear'):
        product = GearBubbleProduct.objects.get(id=product_id)
        permissions.user_can_edit(user, product)
        GearUserUpload.objects.create(user=user.models_user, product=product, url=upload_url[:510])

        if old_url and not old_url == upload_url:
            update_product_data_images(product, old_url, upload_url)

    elif request.GET.get('gkart') or request.POST.get('gkart'):
        product = GrooveKartProduct.objects.get(id=product_id)
        permissions.user_can_edit(user, product)
        GrooveKartUserUpload.objects.create(user=user.models_user, product=product, url=upload_url[:510])

        if old_url and not old_url == upload_url:
            update_product_data_images(product, old_url, upload_url)

    elif request.GET.get('bigcommerce') or request.POST.get('bigcommerce'):
        product = BigCommerceProduct.objects.get(id=product_id)
        permissions.user_can_edit(user, product)

        BigCommerceUserUpload.objects.create(user=user.models_user, product=product, url=upload_url[:510])

        if old_url and not old_url == upload_url:
            update_product_data_images(product, old_url, upload_url)

    elif request.GET.get('ebay') or request.POST.get('ebay'):
        product = EbayProduct.objects.get(id=product_id)

        permissions.user_can_edit(user, product)

        EbayUserUpload.objects.create(user=user.models_user, product=product, url=upload_url[:510])

        if old_url and not old_url == upload_url:
            sd_utils = SureDoneUtils(user=user.models_user, account_id=product.sd_account_id)
            data = sd_utils.update_suredone_product_data_images(product, old_url, upload_url)
            data = json.dumps(data)
            return JsonResponse({
                'status': 'ok',
                'url': upload_url,
                'data': data
            })

    elif request.GET.get('fb') or request.POST.get('fb'):
        product = FBProduct.objects.get(id=product_id)

        permissions.user_can_edit(user, product)

        FBUserUpload.objects.create(user=user.models_user, product=product, url=upload_url[:510])

        if old_url and not old_url == upload_url:
            sd_utils = SureDoneUtils(user=user.models_user, account_id=product.sd_account_id)
            data = sd_utils.update_suredone_product_data_images(product, old_url, upload_url)
            data = json.dumps(data)
            return JsonResponse({
                'status': 'ok',
                'url': upload_url,
                'data': data
            })

    elif request.GET.get('google') or request.POST.get('google'):
        product = GoogleProduct.objects.get(id=product_id)

        permissions.user_can_edit(user, product)

        GoogleUserUpload.objects.create(user=user.models_user, product=product, url=upload_url[:510])

        if old_url and not old_url == upload_url:
            sd_utils = SureDoneUtils(user=user.models_user, account_id=product.sd_account_id)
            data = sd_utils.update_suredone_product_data_images(product, old_url, upload_url)
            data = json.dumps(data)
            return JsonResponse({
                'status': 'ok',
                'url': upload_url,
                'data': data
            })

    else:
        product = ShopifyProduct.objects.get(id=product_id)
        permissions.user_can_edit(user, product)
        UserUpload.objects.create(user=user.models_user, product=product, url=upload_url[:510])

    if 'advanced' in request.GET:
        product.store.pusher_trigger('advanced-editor', {
            'success': True,
            'product': product_id,
            'url': upload_url,
            'image_id': request.GET.get('image_id'),
        })

        json_response = JsonResponse({
            'message': 'Changes applied to image in Dropified',
            'newSource': upload_url
        })

        json_response["Access-Control-Allow-Origin"] = "https://www.photopea.com"
        return json_response

    return JsonResponse({
        'status': 'ok',
        'url': upload_url
    })


class OrdersViewUpsell(TemplateView):
    template_name = 'orders_new.html'

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.orders_ids = []
        self.products_ids = []
        self.orders_track = {}

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)


class OrdersView(AuthenticationMixin, TemplateView):
    template_name = 'orders_new.html'
    post_per_page = 20

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # Template context
        self.ctx = Munch()

        # current User & Store
        self.user = None
        self.models_user = None
        self.store = None

        self.bulk_queue = False  # return JSON-formated data for Bulk Ordering feature

        # User settings, current filter and store sync status
        self.config = Munch()
        self.filters = Munch()
        self.sync = Munch()

        self.page = 0
        self.page_num = 0
        self.page_start = 0

        # Caching
        self.products_cache = {}
        self.orders_ids = []
        self.products_ids = []
        self.orders_track = {}
        self.orders_log = {}
        self.unfulfilled_supplement_items = {}
        self.changed_variants = {}
        self.images_list = {}
        self.products_list_cache = {}

        # ES
        self.es = None

        self.orders = []  # found orders list
        self.paginator = None  # current paginator, can be API, ES or DB paginator
        self.open_orders = None  # Found orders count
        self.current_page = None  # current Page instance returned by paginator

        self.admitad_site_id = None

    # Get temaplte name funcion for TemplateView class
    def get_template_names(self):
        theme = self.request.GET.get('theme')
        if theme:
            self.request.user.set_config('use_old_theme', theme == 'old')

        if self.request.user.get_config('use_old_theme'):
            return ['orders_old.html']
        else:
            return ['orders_new.html']

    def find_orders(self, store, order_id, line_id=None):
        self.store = store
        self.user = store.user
        self.models_user = store.user.models_user

        self.bulk_queue = True

        # set defualt required fields
        self.filters.update(
            query_order=str(order_id),
            query_line_id=safe_str(line_id),
            order_view_live='1',

            created_at_start=None,
            created_at_end=None,
            query_customer_id=None,
            query_address=None,
            query='',
            sort='',

            status=None,
            fulfillment='',
            financial='any',
            connected_only=None,
            awaiting_order=None,
            product_filter=None,
            supplier_filter=None,
            shipping_method_filter=None,
            sort_field='created_at',
            sort_type='true',
        )

        result = self.proccess_orders()
        return format_queueable_orders(result['orders'], result['current_page'], orders_only=True)

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            try:
                self.request.user = self.get_user(request)
            except ApiLoginException:
                return HttpResponseRedirect(app_link(reverse('login'), next=request.get_full_path()))

        if not request.user.can('orders.use'):
            return HttpResponseRedirect(f"{reverse('orders_upsell')}")

        self.user = self.request.user
        self.models_user = self.request.user.models_user

        # Bulk is used to return JSON formatted data for Bulk Ordering feature
        self.bulk_queue = bool(self.request.GET.get('bulk_queue'))
        if self.bulk_queue and not request.user.can('bulk_order.use'):
            return JsonResponse({'error': "Your plan doesn't have Bulk Ordering feature."}, status=402)

        if not self.store:
            # Get or guess the current store from the request
            self.store = utils.get_store_from_request(request)

        if not self.store:
            # TODO: possible redirection loop
            return HttpResponseRedirect(reverse('goto-page', kwargs={'url_name': 'orders_list'}))

        # Check if sub user have access to Orders page
        if not request.user.can('place_orders.sub', self.store):
            messages.warning(request, "You don't have access to this store orders")
            return HttpResponseRedirect('/')

        # Reset user filter settings
        if self.request.GET.get('reset') == '1':
            self.user.profile.del_config_values('_orders_filter_', True)

        admitad_site_id, user_admitad_credentials = utils.get_admitad_credentials(self.request.user.models_user)
        self.admitad_site_id = admitad_site_id if user_admitad_credentials else False

        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        self.get_pagination()
        self.check_extension_version()

        try:
            self.proccess_orders()

        except ApiProcessException as e:
            context['api_error'] = ':'.join(e.args)

        self.get_breadcrumbs()

        context.update(self.ctx)

        return context

    def get_breadcrumbs(self):
        self.ctx.page = 'orders'

        # getting total orders
        self.ctx.total_orders = self.user.profile.get_orders_count(ShopifyOrderTrack)
        self.ctx.autofulfill_limit = self.user.profile.get_auto_fulfill_limit()

        try:
            self.ctx.autofulfill_usage_percent = safe_float(self.ctx.total_orders) / safe_float(
                self.ctx.autofulfill_limit)
        except:
            self.ctx.autofulfill_usage_percent = 0

        if self.ctx.autofulfill_usage_percent > 0.8:
            self.ctx.autofulfill_addons = Addon.objects.filter(auto_fulfill_limit__gt=0, is_active=True).all()
        if self.ctx.autofulfill_limit != -1:
            page_title = 'Orders ({}/{})'.format(self.ctx.total_orders, self.ctx.autofulfill_limit)
        else:
            page_title = 'Orders'
        self.ctx.breadcrumbs = [
            {'url': '/orders', 'title': page_title},
            {'url': f'/orders?store={self.store.id}', 'title': self.store.title},
        ]

    def get_pagination(self):
        pass

    def check_extension_version(self):
        # Check if the extension is up-to-date
        latest_release = cache.get('extension_min_version')
        user_version = self.request.user.get_config('extension_version')

        if user_version and latest_release and version_compare(user_version, latest_release) < 0 and cache.get('extension_required', False):
            messages.warning(
                self.request, 'You are using version <b>{}</b> of the extension, the latest version is <b>{}.</b> '
                '<a href="/pages/13">View Upgrade Instructions</a>'.format(user_version, latest_release))

    def get_user_settings(self):
        # User settings
        self.config.update(
            order_custom_note=self.models_user.get_config('order_custom_note'),
            epacket_shipping=bool(self.models_user.get_config('epacket_shipping')),
            aliexpress_shipping_method=self.models_user.get_config('aliexpress_shipping_method'),
            auto_ordered_mark=bool(self.models_user.get_config('auto_ordered_mark', True)),
            order_custom_line_attr=bool(self.models_user.get_config('order_custom_line_attr')),
            use_relative_dates=bool(self.models_user.get_config('use_relative_dates', True)),
            fix_order_variants=self.models_user.get_config('fix_order_variants'),
            aliexpress_fix_address=self.models_user.get_config('aliexpress_fix_address', True),
            aliexpress_fix_city=self.models_user.get_config('aliexpress_fix_city', True),
            german_umlauts=self.models_user.get_config('_use_german_umlauts', False),
            show_actual_supplier=self.models_user.get_config('_show_actual_supplier', False) or self.models_user.id in [883, 21064, 24767],
            order_risk_all_getaways=self.models_user.get_config('_order_risk_all_getaways', False),
            aliexpress_mobile_order=self.models_user.can('aliexpress_mobile_order.use'),
            ebay_manual_affiliate_link=self.models_user.can('ebay_manual_affiliate_link.use'),
            use_aliexpress_api=self.models_user.can('aliexpress_api_integration.use'),
            aliexpress_account=AliexpressAccount.objects.filter(user=self.models_user),
            aliexpress_order_notes=self.models_user.get_config('aliexpress_order_notes'),
            use_extension_quick=self.models_user.can('aliexpress_extension_quick_order.use'),
        )

        self.config['admitad_site_id'], self.config['user_admitad_credentials'] = utils.get_admitad_credentials(self.models_user)

        return self.config

    def get_filters(self):
        if not hasattr(self, 'request'):
            return

        now = arrow.get(timezone.now())

        self.page = self.request.GET.get('page')
        self.page_num = safe_int(self.request.GET.get('page'), 1)
        self.page_start = safe_int(self.request.GET.get('page_start'), 1)
        self.page_num += self.page_start - 1

        self.filters.update(
            sort=utils.get_orders_filter(self.request, 'sort', 'asc'),
            status=utils.get_orders_filter(self.request, 'status', 'open'),
            fulfillment=utils.get_orders_filter(self.request, 'fulfillment', 'unshipped,partial'),
            financial=utils.get_orders_filter(self.request, 'financial', 'paid,partially_refunded'),
            sort_field=utils.get_orders_filter(self.request, 'sort', 'created_at'),
            sort_type=utils.get_orders_filter(self.request, 'desc', checkbox=True),
            connected_only=utils.get_orders_filter(self.request, 'connected', checkbox=True),
            awaiting_order=utils.get_orders_filter(self.request, 'awaiting_order', checkbox=True),

            query=decode_params(self.request.GET.get('query') or self.request.GET.get('id')),
            query_order=decode_params(self.request.GET.get('query_order') or self.request.GET.get('id')),
            query_line_id=self.request.GET.get('line_id'),
            query_customer=decode_params(self.request.GET.get('query_customer')),
            query_customer_id=self.request.GET.get('query_customer_id'),
            query_address=self.request.GET.getlist('query_address'),

            product_filter=[i for i in self.request.GET.getlist('product') if safe_int(i)],

            supplier_filter=self.request.GET.get('supplier_name'),
            shipping_method_filter=self.request.GET.get('shipping_method_name'),
            exclude_products=self.request.GET.get('exclude_products'),

            order_risk_levels_enabled=self.models_user.get_config('order_risk_levels_enabled'),
            user_filter=utils.get_orders_filter(self.request),

            created_at_daterange=self.request.GET.get('created_at_daterange', now.replace(days=-30).format('MM/DD/YYYY-')),

            order_debug=self.request.session.get('is_hijacked_user') or self.request.user.get_config('_orders_debug') or settings.DEBUG
        )

        if self.filters.product_filter:
            self.filters.product_filter = self.models_user.shopifyproduct_set.filter(id__in=self.filters.product_filter)

        if self.request.GET.get('shop') or self.filters.query or self.filters.query_order or self.filters.query_customer \
                or self.filters.query_customer_id:
            self.filters.status = 'any'
            self.filters.fulfillment = 'any'
            self.filters.financial = 'any'
            self.filters.connected_only = False
            self.filters.awaiting_order = False
            self.filters.created_at_daterange = None

        self.filters.created_at_start, self.filters.created_at_end = None, None
        if self.filters.created_at_daterange:
            try:
                daterange_list = self.filters.created_at_daterange.split('-')

                tz = timezone.localtime(timezone.now()).strftime(' %z')

                self.filters.created_at_start = arrow.get(daterange_list[0] + tz, r'MM/DD/YYYY Z').datetime

                if len(daterange_list) > 1 and daterange_list[1]:
                    self.filters.created_at_end = arrow.get(daterange_list[1] + tz, r'MM/DD/YYYY Z')
                    self.filters.created_at_end = self.filters.created_at_end.span('day')[1].datetime

            except:
                pass

        self.filters.update(
            order_view_old=self.request.GET.get('old'),
            order_view_new=self.request.GET.get('new'),
            order_view_live=self.request.GET.get('live'),
            order_view_elastic=self.request.GET.get('elastic'),
        )

        return self.filters

    def get_sync_status(self):
        if self.filters.get('order_view_old') == '1':
            shopify_orders_utils.disable_store_sync(self.store)
        elif self.filters.get('order_view_old') == '0':
            shopify_orders_utils.enable_store_sync(self.store)

        self.sync.store_order_synced = shopify_orders_utils.is_store_synced(self.store)
        self.sync.store_sync_enabled = self.sync.store_order_synced \
            and (shopify_orders_utils.is_store_sync_enabled(self.store) or self.filters.get('order_view_new')) \
            and not self.filters.get('order_view_live')

        self.sync.support_product_filter = shopify_orders_utils.support_product_filter(self.store) and self.models_user.can('exclude_products.use')
        self.sync.shipping_method_filter_enabled = self.filters.get('shipping_method_filter') and self.sync.store_order_synced

        self.es = shopify_orders_utils.get_elastic()
        self.sync.es_search_enabled = self.es and shopify_orders_utils.is_store_indexed(store=self.store) \
            and not self.filters.get('order_view_elastic') == '0'

        # Start background syncing task
        orders_sync_check_key = f'store_orders_sync_check_{self.store.id}'
        if self.sync.store_sync_enabled and cache.get(orders_sync_check_key) is None:
            cache.set(orders_sync_check_key, True, timeout=43200)
            tasks.sync_shopify_orders.apply_async(
                args=[self.store.id],
                kwargs={'elastic': self.sync.es_search_enabled},
                expires=600)

        return self.sync

    def get_orders(self):
        api_error = None

        try:
            if not self.sync.store_sync_enabled:
                self.get_orders_from_api()
            elif self.sync.es_search_enabled:
                self.get_orders_from_es()
            else:
                self.get_orders_from_db()

        except json.JSONDecodeError:
            api_error = 'Unexpected response content'
            capture_exception()

        except requests.exceptions.ConnectTimeout:
            api_error = 'Connection Timeout'
            capture_exception()

        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 429:
                api_error = 'API Rate Limit'
            elif e.response.status_code == 404:
                api_error = 'Store Not Found'
            elif e.response.status_code == 402:
                api_error = 'Your Shopify Store is not on a paid plan'
            elif e.response.status_code == 503:
                api_error = 'Your Shopify store is temporarily unavailable, please try again later'
            else:
                api_error = 'Shopify API Error {}'.format(e.response.status_code)

            capture_exception()

        except:
            api_error = 'Unknown Error'
            capture_exception()

        if api_error:
            raise ApiProcessException(api_error)

    def get_orders_from_api(self):
        if ',' in self.filters.fulfillment:
            # Direct API call doesn't support more that one fulfillment status
            self.filters.fulfillment = 'unshipped'

        if ',' in self.filters.financial:
            self.filters.financial = 'paid'

        if self.filters.created_at_start:
            self.filters.created_at_start = arrow.get(self.filters.created_at_start).isoformat()

        if self.filters.created_at_end:
            self.filters.created_at_end = arrow.get(self.filters.created_at_end).isoformat()

        if self.filters.query_order and not self.filters.query:
            self.filters.query = self.filters.query_order

        if self.filters.query:
            order_id = shopify_orders_utils.order_id_from_name(self.store, self.filters.query)
        else:
            order_id = None

        paginator = ShopifyOrderPaginator([], self.post_per_page)
        paginator.set_store(self.store)
        paginator.set_page_info(self.page)
        paginator.set_order_limit(self.post_per_page)
        paginator.set_filter(
            self.filters.status,
            self.filters.fulfillment,
            self.filters.financial,
            self.filters.created_at_start,
            self.filters.created_at_end
        )

        paginator.set_reverse_order(self.filters.sort == 'desc' and self.filters.sort != 'created_at')
        paginator.set_query(safe_int(order_id, self.filters.query))

        self.paginator = paginator
        self.open_orders = paginator.orders_count()

        self.page_num = min(max(1, self.page_num), paginator.num_pages)
        self.current_page = paginator.page(self.page_num)

        db_page = ShopifyOrder.objects.filter(store=self.store, order_id__in=[i['id'] for i in self.current_page])
        _update_page = shopify_orders_utils.sort_orders(self.current_page, db_page)
        self.sync_orders_with_db(_update_page)

    def get_orders_from_es(self):
        _must_term = [{'term': {'store': self.store.id}}]
        _must_not_term = []

        if self.filters.query_order:
            order_id = shopify_orders_utils.order_id_from_name(self.store, self.filters.query_order)

            if order_id:
                _must_term.append({'term': {'order_id': order_id}})
            else:
                source_id = self.filters.query_order.replace('#', '').strip()
                order_ids = ShopifyOrderTrack.objects.filter(store=self.store, source_id=source_id) \
                                                     .defer('data') \
                                                     .values_list('order_id', flat=True)
                if len(order_ids):
                    _must_term.append({
                        'bool': {
                            'should': [{'term': {'order_id': i}} for i in order_ids]
                        }
                    })
                else:
                    _must_term.append({'term': {'order_id': safe_int(self.filters.query_order, 0)}})

        if self.filters.status == 'open':
            _must_not_term.append({"exists": {'field': 'closed_at'}})
            _must_not_term.append({"exists": {'field': 'cancelled_at'}})
        elif self.filters.status == 'closed':
            _must_term.append({"exists": {'field': 'closed_at'}})
        elif self.filters.status == 'cancelled':
            _must_term.append({"exists": {'field': 'cancelled_at'}})

        if self.filters.fulfillment == 'unshipped,partial':
            _must_term.append({
                'bool': {
                    'should': [
                        {
                            'bool': {
                                'must_not': [
                                    {"exists": {'field': 'fulfillment_status'}}
                                ]
                            }
                        },
                        {'term': {'fulfillment_status': 'partial'}}
                    ]
                }
            })
        elif self.filters.fulfillment == 'unshipped':
            _must_not_term.append({"exists": {'field': 'fulfillment_status'}})
        elif self.filters.fulfillment == 'shipped':
            _must_term.append({'term': {'fulfillment_status': 'fulfilled'}})
        elif self.filters.fulfillment == 'partial':
            _must_term.append({'term': {'fulfillment_status': 'partial'}})

        if self.filters.financial == 'paid,partially_refunded':
            _must_term.append({
                'bool': {
                    'should': [
                        {'term': {'financial_status': 'paid'}},
                        {'term': {'financial_status': 'partially_refunded'}}
                    ]
                }
            })
        elif self.filters.financial != 'any':
            _must_term.append({'term': {'financial_status': self.filters.financial}})

        if self.filters.query_customer_id:
            # Search by customer ID first
            _must_term.append({'match': {'customer_id': self.filters.query_customer_id}})

        elif self.filters.query_customer:
            # Try to find the customer email in the search query
            customer_email = re.findall(r'[\w\._\+-]+@[\w\.-]+', self.filters.query_customer)

            if customer_email:
                _must_term.append({'match': {'customer_email': customer_email[0].lower()}})
            else:
                _must_term.append({'match': {'customer_name': self.filters.query_customer.lower()}})

        if self.filters.query_address and len(self.filters.query_address):
            # Note: query_address must be lower-cased depending on the Elasticsearch cluster used (probably the default analyzer)
            # Our production require country codes to be uppercase
            _must_term.append({
                'terms': {'country_code': self.filters.query_address}
            })

        if self.filters.created_at_start and self.filters.created_at_end:
            _must_term.append({
                "range": {
                    "created_at": {
                        "gte": self.filters.created_at_start.isoformat(),
                        "lte": self.filters.created_at_end.isoformat(),
                    }
                }
            })
        elif self.filters.created_at_start:
            _must_term.append({
                "range": {
                    "created_at": {
                        "gte": self.filters.created_at_start.isoformat(),
                    }
                }
            })
        elif self.filters.created_at_end:
            _must_term.append({
                "range": {
                    "created_at": {
                        "lte": self.filters.created_at_end.isoformat(),
                    }
                }
            })

        if self.filters.connected_only == 'true':
            _must_term.append({
                'range': {
                    'connected_items': {
                        'gt': 0
                    }
                }
            })

        if self.filters.awaiting_order == 'true':
            _must_term.append({
                'range': {
                    'need_fulfillment': {
                        'gt': 0
                    }
                }
            })

        product_ids_search = []
        if self.filters.product_filter:
            product_ids_search += [product.id for product in self.filters.product_filter]

        if self.filters.supplier_filter:
            products = ShopifyProduct.objects.filter(default_supplier__supplier_name=self.filters.supplier_filter)
            product_ids_search += [product.id for product in products]

        if product_ids_search:
            _must_term.append({
                'terms': {
                    'product_ids': list(set(product_ids_search))
                }
            })

        if self.filters.sort_field not in ['created_at', 'updated_at', 'total_price', 'country_code']:
            self.filters.sort_field = 'created_at'

        body = {
            'query': {
                'bool': {
                    'must': _must_term,
                    'must_not': _must_not_term
                },
            },
            'sort': [{
                self.filters.sort_field: 'desc' if self.filters.sort_type == 'true' else 'asc'
            }],
            'size': self.post_per_page,
            'from': (self.page_num - 1) * self.post_per_page
        }

        matchs = self.es.search(index='shopify-order', doc_type='order', body=body)
        hits = matchs['hits']['hits']
        orders = ShopifyOrder.objects.filter(id__in=[i['_id'] for i in hits])
        paginator = FakePaginator(range(0, matchs['hits']['total']), self.post_per_page)
        paginator.set_orders(orders)

        page_num = min(max(1, self.page_num), paginator.num_pages)
        self.current_page = paginator.page(page_num)
        self.paginator = paginator
        self.open_orders = matchs['hits']['total']

        if matchs['hits']['total']:
            rep = requests.get(
                url=self.store.api('orders'),
                params={
                    'ids': ','.join([str(i['_source']['order_id']) for i in hits]),
                    'status': 'any',
                    'fulfillment_status': 'any',
                    'financial_status': 'any',
                }
            )

            rep.raise_for_status()
            shopify_orders = rep.json()['orders']
            db_orders = ShopifyOrder.objects.filter(id__in=[i['_id'] for i in hits]) \
                                            .only('order_id', 'updated_at', 'closed_at', 'cancelled_at')

            self.current_page.object_list = shopify_orders_utils.sort_es_orders(shopify_orders, hits, db_orders)

            self.sync_order_with_db_from_es(self.current_page)

    def get_orders_from_db(self):
        orders = ShopifyOrder.objects.filter(store=self.store).only('order_id', 'updated_at', 'closed_at', 'cancelled_at')

        if ShopifySyncStatus.objects.get(store=self.store).sync_status == 6:
            messages.info(self.request, 'Your Store Orders are being imported')

        if self.filters.query_order:
            order_id = shopify_orders_utils.order_id_from_name(self.store, self.filters.query_order)

            if order_id:
                orders = orders.filter(order_id=order_id)
            else:
                source_id = self.filters.query_order.replace('#', '').strip()
                order_ids = ShopifyOrderTrack.objects.filter(store=self.store, source_id=source_id) \
                                                     .defer('data') \
                                                     .values_list('order_id', flat=True)
                if len(order_ids):
                    orders = orders.filter(order_id__in=order_ids)
                else:
                    orders = orders.filter(order_id=safe_int(self.filters.query_order, 0))

        if self.filters.created_at_start:
            orders = orders.filter(created_at__gte=self.filters.created_at_start)

        if self.filters.created_at_end:
            orders = orders.filter(created_at__lte=self.filters.created_at_end)

        if safe_int(self.filters.query_customer_id):
            order_ids = shopify_orders_utils.order_ids_from_customer_id(self.store, self.filters.query_customer_id)
            if len(order_ids):
                orders = orders.filter(order_id__in=order_ids)
            else:
                orders = orders.filter(order_id=-1)  # Show Not Found message

        if self.filters.query_address and len(self.filters.query_address):
            orders = orders.filter(Q(country_code__in=self.filters.query_address))

        self.filters.query = None

        if self.filters.status == 'open':
            orders = orders.filter(closed_at=None, cancelled_at=None)
        elif self.filters.status == 'closed':
            orders = orders.exclude(closed_at=None)
        elif self.filters.status == 'cancelled':
            orders = orders.exclude(cancelled_at=None)

        if self.filters.fulfillment == 'unshipped,partial':
            orders = orders.filter(Q(fulfillment_status=None) | Q(fulfillment_status='partial'))
        elif self.filters.fulfillment == 'unshipped':
            orders = orders.filter(fulfillment_status=None)
        elif self.filters.fulfillment == 'shipped':
            orders = orders.filter(fulfillment_status='fulfilled')
        elif self.filters.fulfillment == 'partial':
            orders = orders.filter(fulfillment_status='partial')

        if self.filters.financial == 'paid,partially_refunded':
            orders = orders.filter(Q(financial_status='paid') | Q(financial_status='partially_refunded'))
        elif self.filters.financial != 'any':
            orders = orders.filter(financial_status=self.filters.financial)

        if self.filters.connected_only == 'true':
            if self.sync.support_product_filter:
                orders = orders.filter(connected_items__gt=0)
            else:
                orders = orders.annotate(connected=Max('shopifyorderline__product_id')).filter(connected__gt=0)

        if self.filters.awaiting_order == 'true':
            if self.sync.support_product_filter:
                orders = orders.filter(need_fulfillment__gt=0)
            else:
                orders = orders.annotate(tracked=Count('shopifyorderline__track')).exclude(tracked=F('items_count'))

        if self.filters.product_filter:
            if self.filters.get('exclude_products'):
                orders = orders.exclude(shopifyorderline__product_id__in=self.filters.product_filter,
                                        items_count__lte=len(self.filters.product_filter)).distinct()
            else:
                orders = orders.filter(shopifyorderline__product_id__in=self.filters.product_filter).distinct()

        if self.filters.supplier_filter:
            orders = orders.filter(shopifyorderline__product__default_supplier__supplier_name=self.filters.supplier_filter).distinct()

        if self.filters.shipping_method_filter:
            orders = orders.filter(shipping_lines__title=self.filters.shipping_method_filter)

        if self.filters.sort_field in ['created_at', 'updated_at', 'total_price', 'country_code']:
            sort_desc = '-' if self.filters.sort_type == 'true' else ''

            if self.filters.sort_field == 'created_at':
                self.filters.sort_field = 'order_id'

            orders = orders.order_by(sort_desc + self.filters.sort_field)

        paginator = SimplePaginator(orders, self.post_per_page)
        page_num = min(max(1, self.page_num), paginator.num_pages)

        self.current_page = paginator.page(page_num)
        self.open_orders = paginator.count
        self.paginator = paginator

        if self.current_page.object_list:
            rep = requests.get(
                url=self.store.api('orders'),
                params={
                    'ids': ','.join([str(i.order_id) for i in self.current_page]),
                    'status': 'any',
                    'fulfillment_status': 'any',
                    'financial_status': 'any',
                }
            )

            rep.raise_for_status()

            shopify_orders = rep.json()['orders']

            self.current_page.object_list = shopify_orders_utils.sort_orders(shopify_orders, self.current_page)

            self.sync_orders_with_db_from_api(self.current_page)

    def sync_orders_with_db(self, current_page):
        countdown = 1
        for order in current_page:
            if arrow.get(order['updated_at']).timestamp > order['db_updated_at']:
                tasks.update_shopify_order.apply_async(
                    args=[self.store.id, order['id']],
                    kwargs={'shopify_order': order, 'from_webhook': False},
                    countdown=countdown)

                countdown = countdown + 1

    def sync_order_with_db_from_es(self, current_page):
        countdown = 1
        for order in current_page:
            shopify_update_at = arrow.get(order['updated_at']).timestamp
            if shopify_update_at > order['db_updated_at'] or shopify_update_at > order['es_updated_at']:

                tasks.update_shopify_order.apply_async(
                    args=[self.store.id, order['id']],
                    kwargs={'shopify_order': order, 'from_webhook': False},
                    countdown=countdown,
                    expires=1800)

                countdown = countdown + 1

    def sync_orders_with_db_from_api(self, current_page):
        countdown = 1
        for order in current_page:
            if arrow.get(order['updated_at']).timestamp > order['db_updated_at']:
                tasks.update_shopify_order.apply_async(
                    args=[self.store.id, order['id']],
                    kwargs={'shopify_order': order, 'from_webhook': False},
                    countdown=countdown,
                    expires=1800)

                countdown = countdown + 1

    def filter_orders(self):
        for order in self.current_page:
            line_items = []
            for line in order['line_items']:
                if type(line.get('tip')) is dict:
                    order['total_tip'] = line['price']
                    continue

                line_items.append(line)

            order['line_items'] = line_items

    def load_models_cache(self):
        for order in self.current_page:
            self.orders_ids.append(order['id'])
            for line in order['line_items']:
                if line['product_id']:
                    self.products_ids.append(line['product_id'])

        for i in ShopifyOrderTrack.objects.filter(store=self.store, order_id__in=self.orders_ids).defer('data'):
            self.orders_track['{}-{}'.format(i.order_id, i.line_id)] = i

        for i in ShopifyOrderLog.objects.filter(store=self.store, order_id__in=self.orders_ids):
            self.orders_log[i.order_id] = i

        for i in ShopifyOrderVariant.objects.filter(store=self.store, order_id__in=self.orders_ids):
            self.changed_variants['{}-{}'.format(i.order_id, i.line_id)] = i

        res = ShopifyProductImage.objects.filter(store=self.store, product__in=self.products_ids)
        for i in res:
            self.images_list['{}-{}'.format(i.product, i.variant)] = i.image

        for p in ShopifyProduct.objects.filter(store=self.store, shopify_id__in=self.products_ids).select_related('default_supplier'):
            if p.shopify_id not in self.products_list_cache:
                self.products_list_cache[p.shopify_id] = p

        for o in PLSOrder.objects.prefetch_related('order_items',
                                                   'order_items__label',
                                                   'order_items__label__user_supplement'
                                                   ).filter(is_fulfilled=False,
                                                            store_type='shopify',
                                                            store_id=self.store.id,
                                                            store_order_id__in=self.orders_ids):
            for i in o.order_items.all():
                item_key = f'{i.store_order_id}-{i.line_id}'
                # Store order single items can become multiple items (bundles)
                if not self.unfulfilled_supplement_items.get(item_key):
                    self.unfulfilled_supplement_items[item_key] = []
                self.unfulfilled_supplement_items[item_key].append(i)

    def proccess_orders(self):
        self.get_user_settings()
        self.get_filters()
        self.get_sync_status()

        self.get_orders()
        self.filter_orders()

        self.load_models_cache()

        orders_cache = {}
        raw_orders_cache = {}
        open_print_on_demand = False
        for index, order in enumerate(self.current_page):
            created_at = arrow.get(order['created_at'])
            try:
                created_at = created_at.to(self.request.session['django_timezone'])
            except:
                pass

            order['date'] = created_at
            order['date_str'] = created_at.format('MM/DD/YYYY')
            order['date_tooltip'] = created_at.format('YYYY/MM/DD HH:mm:ss')
            order['order_url'] = self.store.get_link('/admin/orders/%d' % order['id'])
            order['order_api_url'] = self.store.api('orders', order['id'])
            order['store'] = self.store
            order['placed_orders'] = 0
            order['connected_lines'] = 0
            order['lines_count'] = len(order['line_items'])
            order['refunded_lines'] = []
            order['order_log'] = self.orders_log.get(order['id'])
            order['supplier_types'] = set()
            order['is_fulfilled'] = order.get('fulfillment_status') == 'fulfilled'
            order['pending_payment'] = (order['financial_status'] == 'pending'
                                        and (order['gateway'] == 'paypal' or 'amazon' in order['gateway'].lower()))
            update_shipstation_items = {}
            shipstation_address_changed = None

            if type(order['refunds']) is list:
                for refund in order['refunds']:
                    for refund_line in refund['refund_line_items']:
                        order['refunded_lines'].append(refund_line['line_item_id'])

            query_line_id = safe_int(self.filters.get('query_line_id'))
            if query_line_id:
                order['line_items'] = [i for i in order['line_items'] if i['id'] == query_line_id]

            for i, line_item in enumerate(order['line_items']):
                line_item['refunded'] = line_item['id'] in order['refunded_lines']

                line_item['image'] = {
                    'store': self.store.id,
                    'product': line_item['product_id'],
                    'variant': line_item['variant_id']
                }

                line_item['image_src'] = self.images_list.get('{}-{}'.format(line_item['product_id'], line_item['variant_id']))

                order_track = self.orders_track.get('{}-{}'.format(order['id'], line_item['id']))
                changed_variant = self.changed_variants.get('{}-{}'.format(order['id'], line_item['id']))

                line_item['order_track'] = order_track
                line_item['changed_variant'] = changed_variant

                variant_id = changed_variant.variant_id if changed_variant else line_item['variant_id']
                variant_title = changed_variant.variant_title if changed_variant else line_item['variant_title']

                line_item['variant_link'] = self.store.get_link('/admin/products/{}/variants/{}'.format(line_item['product_id'], variant_id))

                if not line_item['product_id']:
                    if variant_id:
                        product = ShopifyProduct.objects.filter(store=self.store, title=line_item['title'], shopify_id__gt=0).first()
                    else:
                        product = None
                elif line_item['product_id'] in self.products_cache:
                    product = self.products_cache[line_item['product_id']]
                else:
                    product = self.products_list_cache.get(line_item['product_id'])

                if order_track or line_item['fulfillment_status'] == 'fulfilled' or (product and product.is_excluded):
                    order['placed_orders'] += 1

                country_code = order.get('shipping_address', {}).get('country_code')
                if not country_code:
                    country_code = order.get('customer', {}).get('default_address', {}).get('country_code')

                logistics_address = None
                if self.models_user.can('logistics.use'):
                    logistics_address = utils.shopify_customer_address(
                        order,
                        german_umlauts=self.config.german_umlauts,
                        shipstation_fix=True
                    )[1]

                    if not order['pending_payment'] and (not product or not product.have_supplier()):
                        try:
                            raw_order_id = f"raw_{self.store.id}_{order['id']}_{line_item['id']}"
                            line_item['raw_order_data_id'] = raw_order_id
                            raw_orders_cache[f"order_{raw_order_id}"] = {
                                'id': '{}_{}_{}'.format(self.store.id, order['id'], line_item['id']),
                                'order_name': order['name'],
                                'title': line_item['title'],
                                'quantity': line_item['quantity'],
                                'weight': line_item.get('weight'),
                                'logistics_address': logistics_address,
                                'shipping_method': line_item.get('shipping_method'),
                                'order_id': order['id'],
                                'line_id': line_item['id'],
                                'product_id': line_item['product_id'],
                                'variants': (line_item['variant_title'] or '').split(' / '),
                                'total': safe_float(line_item['price'], 0.0),
                                'store': self.store.id,
                                'is_refunded': line_item['refunded'],
                                'is_raw': True,
                                'order': {
                                    'phone': {
                                        'number': logistics_address.get('phone') if logistics_address else None,
                                        'country': logistics_address['country_code'] if logistics_address else None
                                    },
                                }
                            }
                        except:
                            capture_exception()

                supplier = None
                bundle_data = []
                if product and product.have_supplier():
                    if changed_variant:
                        variant_id = changed_variant.variant_id
                        variant_title = changed_variant.variant_title

                        line_item['variant_id'] = variant_id
                        line_item['variant_title'] = variant_title
                    else:
                        variant_id = product.get_real_variant_id(variant_id)

                    supplier = product.get_supplier_for_variant(variant_id)
                    if supplier:
                        shipping_method = product.get_shipping_for_variant(
                            supplier_id=supplier.id,
                            variant_id=variant_id,
                            country_code=country_code)
                    else:
                        shipping_method = None

                    line_item['product'] = product
                    is_pls = line_item['is_pls'] = supplier.is_pls
                    if is_pls:
                        # pass orders without PLS products (when one store is used in multiple account)
                        try:
                            line_item['weight'] = supplier.user_supplement.get_weight(line_item['quantity'])
                        except:
                            line_item['weight'] = False

                        pls_items = self.unfulfilled_supplement_items.get(f"{order['id']}-{line_item['id']}")
                        if pls_items:  # Item is not fulfilled yet
                            if shipstation_address_changed is None:  # Check only once
                                shipstation_address = utils.shopify_customer_address(
                                    order,
                                    german_umlauts=self.config.german_umlauts,
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
                                    'title': line_item['variant_title'],
                                    'sku': pls_item.sku or pls_item.label.user_supplement.shipstation_sku,
                                    'user_supplement_id': pls_item.label.user_supplement.id,
                                    'label_id': pls_item.label_id,
                                    'image_url': line_item['image_src'],
                                })

                    line_item['is_paid'] = False
                    line_item['supplier'] = supplier
                    line_item['shipping_method'] = shipping_method
                    line_item['supplier_type'] = supplier.supplier_type()

                    if supplier:
                        order['supplier_types'].add(supplier.supplier_type())

                    if self.config.fix_order_variants and supplier.is_aliexpress:
                        mapped = product.get_variant_mapping(name=variant_id, for_extension=True, mapping_supplier=True)
                        if not mapped:
                            utils.fix_order_variants(self.store, order, product)

                    bundles = product.get_bundle_mapping(variant_id)
                    if bundles:
                        product_bundles = []
                        for idx, b in enumerate(bundles):
                            b_product = ShopifyProduct.objects.filter(id=b['id']).select_related('default_supplier').first()
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

                            line_item['is_pls'] = b_supplier.is_pls or line_item['is_pls']
                            b_variant_mapping = b_product.get_variant_mapping(name=b_variant_id, for_extension=True, mapping_supplier=True)
                            if b_variant_id and b_variant_mapping:
                                b_variants = b_variant_mapping
                            else:
                                b_variants = b['variant_title'].split('/') if b['variant_title'] else ''

                            quantity = b['quantity'] * line_item['quantity']
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
                                'order_url': app_link('orders/place', supplier=b_supplier.id, SABundle=True),
                                'variants': b_variants,
                                'shipping_method': b_shipping_method,
                                'country_code': country_code,
                                'supplier_type': b_supplier.supplier_type(),
                            })

                        line_item['bundles'] = product_bundles
                        line_item['is_bundle'] = len(bundle_data) > 0
                        order['have_bundle'] = True

                    order['connected_lines'] += 1

                self.products_cache[line_item['product_id']] = product

                order, customer_address, order['corrections'] = utils.shopify_customer_address(
                    order=order,
                    aliexpress_fix=self.config.aliexpress_fix_address and supplier and supplier.is_aliexpress,
                    aliexpress_fix_city=self.config.aliexpress_fix_city,
                    german_umlauts=self.config.german_umlauts,
                    return_corrections=True,
                    shipstation_fix=supplier.is_pls if supplier else False)

                if customer_address and not order['pending_payment']:
                    try:
                        order_data = {
                            'id': '{}_{}_{}'.format(self.store.id, order['id'], line_item['id']),
                            'order_name': order['name'],
                            'title': line_item['title'],
                            'quantity': line_item['quantity'],
                            'weight': line_item.get('weight'),
                            'shipping_address': customer_address,
                            'shipping_method': line_item.get('shipping_method'),
                            'logistics_address': logistics_address,
                            'order_id': order['id'],
                            'line_id': line_item['id'],
                            'product_id': product.id if product else None,
                            'source_id': supplier.get_source_id() if supplier else None,
                            'supplier_id': supplier.get_store_id() if supplier else None,
                            'supplier_type': supplier.supplier_type() if supplier else None,
                            'total': safe_float(line_item['price'], 0.0),
                            'store': self.store.id,
                            'order': {
                                'phone': {
                                    'number': customer_address.get('phone'),
                                    'country': customer_address['country_code']
                                },
                                'note': self.config.order_custom_note,
                                'epacket': self.config.epacket_shipping,
                                'aliexpress_shipping_method': self.config.aliexpress_shipping_method,
                                'auto_mark': self.config.auto_ordered_mark,
                            },
                            'is_refunded': line_item['refunded'],
                            'products': bundle_data,
                            'is_bundle': len(bundle_data) > 0
                        }

                        if self.config.order_custom_line_attr and line_item.get('properties'):
                            item_note = ''

                            for prop in line_item['properties']:
                                if not prop['name'] or prop['name'].startswith('_'):
                                    continue

                                item_note = '{}{}: {}\n'.format(item_note, prop['name'], prop['value'])

                            if item_note:
                                if not self.models_user.get_config('_plain_attribute_note'):
                                    item_note = 'Here are custom information for the ordered product:\n{}'.format(item_note).strip()
                                else:
                                    item_note = item_note.strip()

                                order_data['order']['item_note'] = item_note
                                line_item['item_note'] = item_note

                        if product:
                            mapped = product.get_variant_mapping(name=variant_id, for_extension=True, mapping_supplier=True)
                            if variant_id and mapped:
                                order_data['variant'] = mapped
                            else:
                                order_data['variant'] = variant_title.split('/') if variant_title else ''

                        if product and product.have_supplier():
                            order_data = fix_order_data(self.user, order_data)
                            orders_cache['order_{}'.format(order_data['id'])] = order_data
                            line_item['order_data_id'] = order_data['id']

                            line_item['order_data'] = order_data

                            if supplier.is_dropified_print:
                                open_print_on_demand = True
                    except:
                        capture_exception()

            order['mixed_supplier_types'] = len(order['supplier_types']) > 1
            self.orders.append(order)

            if shipstation_address_changed:
                # Order items can be placed separately at shipstation
                for pls_order_id, line_items in update_shipstation_items.items():
                    update_shipstation_address.apply_async(
                        args=[pls_order_id, self.store.id, 'shopify'],
                        countdown=5
                    )

        active_orders = {}
        for i in self.orders_ids:
            active_orders['active_order_{}'.format(i)] = True

        caches['orders'].set_many(raw_orders_cache, timeout=86400 if self.bulk_queue else 21600)
        caches['orders'].set_many(orders_cache, timeout=86400 if self.bulk_queue else 21600)
        caches['orders'].set_many(active_orders, timeout=86400 if self.bulk_queue else 3600)

        if self.sync.store_order_synced:
            countries = get_counrties_list()
        else:
            countries = []

        self.ctx.update(
            orders=self.orders,
            store=self.store,
            paginator=self.paginator,
            current_page=self.current_page,
            open_orders=self.open_orders,
            countries=countries,
            open_print_on_demand=open_print_on_demand,
            **self.config,
            **self.filters,
            **self.sync,
        )

        return self.ctx

    def render_to_response(self, context, **response_kwargs):
        if self.bulk_queue:
            return format_queueable_orders(self.orders, self.current_page, request=self.request)
        else:
            return super().render_to_response(context, **response_kwargs)


@login_required
def orders_track(request):
    if not request.user.can('orders.use'):
        return HttpResponseRedirect(f"{reverse('orders_upsell')}")

    try:
        assert not request.is_ajax(), 'AJAX Request Detected - Orders Track'
    except:
        capture_exception(level='warning')

    visited_time = arrow.now().timestamp
    request.user.profile.set_config_value('orders_track_visited_at', visited_time)

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

    sorting = request.GET.get('sort', 'update')
    order_desc = request.GET.get('desc', 'true')
    if sorting:
        if order_desc == 'true':
            sorting = f"-{sorting}"
    sorting = order_map.get(sorting, 'status_updated_at')

    post_per_page = safe_int(request.GET.get('ppp'), 20)
    page = safe_int(request.GET.get('page'), 1)
    query = request.GET.get('query')
    tracking_filter = request.GET.get('tracking')
    fulfillment_filter = request.GET.get('fulfillment')
    hidden_filter = request.GET.get('hidden')
    completed = request.GET.get('completed')
    source_reason = request.GET.get('reason')
    days_passed = request.GET.get('days_passed', '')

    default_date = '{}-'.format(arrow.get(timezone.now()).replace(days=-30).format('MM/DD/YYYY'))
    if settings.DEBUG:
        default_date = None

    date = request.GET.get('date', default_date)

    if query:
        date = None

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
        days_passed = request.user.get_config('sync_delay_notify_days')
        fulfillment_filter = '0'
        tracking_filter = '0'
        hidden_filter = '0'

    store = utils.get_store_from_request(request)
    if not store:
        return HttpResponseRedirect(reverse('goto-page', kwargs={'url_name': 'orders_track'}))

    if not request.user.can('place_orders.sub', store):
        messages.warning(request, "You don't have access to this store orders")
        return HttpResponseRedirect('/')

    orders = using_replica(ShopifyOrderTrack).select_related('store', 'user', 'user__profile') \
                                             .filter(user=request.user.models_user, store=store)

    if query:
        order_id = shopify_orders_utils.order_id_from_name(store, query)

        if order_id:
            orders = orders.filter(order_id=order_id)
        else:
            orders = orders.filter(Q(source_id=clean_query_id(query))
                                   | Q(source_tracking=query))

    if tracking_filter == '0':
        orders = orders.filter(source_tracking='')
    elif tracking_filter == '1':
        orders = orders.exclude(source_tracking='')

    if fulfillment_filter == '1':
        orders = orders.filter(shopify_status='fulfilled')
    elif fulfillment_filter == '0':
        orders = orders.exclude(shopify_status='fulfilled')

    if hidden_filter == '1':
        orders = orders.filter(hidden=True)
    elif not hidden_filter or hidden_filter == '0':
        orders = orders.exclude(hidden=True)

    if completed == '1':
        orders = orders.exclude(source_status='FINISH')

    if source_reason:
        if source_reason.startswith('_'):
            orders = orders.filter(source_status=source_reason[1:])
        else:
            orders = orders.filter(source_status_details=source_reason)

    errors_list = request.GET.getlist('errors')
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
        days_passed = min(days_passed, 360)
        time_threshold = timezone.now() - timezone.timedelta(days=days_passed)
        orders = orders.filter(created_at__lt=time_threshold)

    if created_at_start:
        orders = orders.filter(created_at__gte=created_at_start)

    if created_at_end:
        orders = orders.filter(created_at__lte=created_at_end)

    sync_delay_notify_days = safe_int(request.user.get_config('sync_delay_notify_days'))
    sync_delay_notify_highlight = request.user.get_config('sync_delay_notify_highlight')
    order_threshold = None
    if sync_delay_notify_days > 0 and sync_delay_notify_highlight:
        order_threshold = timezone.now() - timezone.timedelta(days=sync_delay_notify_days)

    orders = orders.order_by(sorting)

    paginator = InfinitePaginator(orders, post_per_page)
    page = paginator.page(page)
    orders = page.object_list

    if len(orders):
        orders = utils.get_tracking_orders(store, orders)

    return render(request, 'orders_track.html', {
        'store': store,
        'use_aliexpress_api': request.user.models_user.can('aliexpress_api_integration.use'),
        'aliexpress_account_count': AliexpressAccount.objects.filter(user=request.user.models_user).count(),
        'orders': orders,
        'date': date,
        'order_threshold': order_threshold,
        'paginator': paginator,
        'current_page': page,
        'errors': errors_list,
        'reason': source_reason,
        'rejected_status': ALIEXPRESS_REJECTED_STATUS,
        'page': 'orders_track',
        'breadcrumbs': [{'title': 'Orders', 'url': '/orders'}, 'Tracking', store.title]
    })


@login_required
def orders_place(request):
    if not request.user.can('auto_order.use'):
        messages.error(request, "Your plan does not allow auto-ordering.")
        return HttpResponseRedirect('/orders')

    product = None
    supplier = None
    disable_affiliate = request.user.get_config('_disable_affiliate', False)

    if request.GET.get('nff'):
        disable_affiliate = True

    if request.GET.get('supplier'):
        supplier = get_object_or_404(ProductSupplier, id=request.GET['supplier'])
        permissions.user_can_view(request.user, supplier.product)

        product = supplier.short_product_url()

    elif request.GET.get('product'):
        product = request.GET['product']

        if safe_int(product):
            product = 'https://www.aliexpress.com/item/{}.html'.format(product)

    if not product:
        return Http404("Product or Order not set")

    if request.GET.get('m'):
        product = product.replace('www.aliexpress.com', 'm.aliexpress.com')

    ali_api_key, ali_tracking_id, user_ali_credentials = utils.get_aliexpress_credentials(request.user.models_user)
    admitad_site_id, user_admitad_credentials = utils.get_admitad_credentials(request.user.models_user)

    if user_admitad_credentials:
        service = 'admitad'
    elif user_ali_credentials:
        service = 'ali'
    else:
        service = settings.DEFAULT_ALIEXPRESS_AFFILIATE

    redirect_url = False

    if not disable_affiliate:
        if request.user.get_config('_disable_affiliate_permanent'):
            disable_affiliate = True

    if not disable_affiliate:
        if supplier and supplier.is_ebay:
            if not request.user.models_user.can('ebay_auto_fulfill.use'):
                messages.error(request, "eBay 1-Click fulfillment is not available on your current plan. "
                                        "Please upgrade to Premier Plan to use this feature")

                return HttpResponseRedirect('/')

            redirect_url = utils.get_ebay_affiliate_url(product)
        else:

            if service == 'ali' and ali_api_key and ali_tracking_id:
                redirect_url = utils.get_aliexpress_affiliate_url(ali_api_key, ali_tracking_id, product)

            elif service == 'admitad':
                redirect_url = utils.get_admitad_affiliate_url(admitad_site_id, product, user=request.user)

    if not redirect_url:
        redirect_url = product

    for k in list(request.GET.keys()):
        if k.startswith('SA') and k not in redirect_url and request.GET[k]:
            redirect_url = utils.affiliate_link_set_query(redirect_url, k, request.GET[k])

    # quick extension ordering url rewrite
    if request.GET.get('quick-order'):
        if not request.user.models_user.can('aliexpress_extension_quick_order.use'):
            messages.error(request, "Extension Quick Ordering is not available on your current plan. "
                                    "Please upgrade to use this feature")
            return HttpResponseRedirect('/')

        # redirect to shoppping cart directly
        redirect_url = 'https://www.aliexpress.com/p/trade/confirm.html?objectId=' + request.GET.get('objectId') + \
                       '&skuId=' + request.GET.get('skuId') + '&quantity=' + request.GET.get('quantity') + \
                       '&SAConfirmOrder=' + request.GET.get('SAPlaceOrder') + '&quick-order=1'

    # Verify if the user didn't pass order limit
    parent_user = request.user.models_user
    plan = parent_user.profile.plan

    auto_fulfill_limit = parent_user.profile.get_auto_fulfill_limit()
    if auto_fulfill_limit != -1:
        orders_count = parent_user.profile.get_orders_count(ShopifyOrderTrack)

        if not settings.DEBUG and not auto_fulfill_limit or orders_count + 1 > auto_fulfill_limit:
            messages.error(request, "Woohoo! 🎉. You are growing and you've hit your orders limit for this month."
                                    " Upgrade now to keep placing orders or wait until next "
                                    "month for your limit to reset.")
            return HttpResponseRedirect('/')

    # Save Auto fulfill event
    event_key = None
    store = None
    event_data = {}
    order_data = None
    order_key = request.GET.get('SAPlaceOrder')
    if order_key:
        event_key = 'keen_event_{}'.format(request.GET['SAPlaceOrder'])

        if not order_key.startswith('order_'):
            order_key = 'order_{}'.format(order_key)

        order_data = order_data_cache(order_key)
        prefix, store, order, line = order_key.split('_')

    if request.user.get_config('extension_version') == '3.41.0':
        # Fix for ePacket selection issue
        shipping_method = request.user.models_user.get_config('aliexpress_shipping_method')
        if supplier and supplier.is_aliexpress and 'SACompany' not in request.GET and shipping_method and shipping_method != 'EMS_ZX_ZX_US':
            return HttpResponseRedirect('{}&SACompany={}'.format(re.sub(r'&$', '', request.get_full_path()), shipping_method))

    if order_data:
        order_data['url'] = redirect_url
        caches['orders'].set(order_key, order_data, timeout=caches['orders'].ttl(order_key))

    if order_data and settings.KEEN_PROJECT_ID and not cache.get(event_key):
        try:
            store = ShopifyStore.objects.get(id=store)
            permissions.user_can_view(request.user, store)
        except ShopifyStore.DoesNotExist:
            raise Http404('Store not found')

        for k in list(request.GET.keys()):
            if k == 'SAPlaceOrder':
                event_data['data_id'] = request.GET[k]

            elif k == 'product':
                event_data['product'] = request.GET[k]

                if not safe_int(event_data['product']):  # Check if we are using product link or just the ID
                    event_data['product'] = re.findall('[/_]([0-9]+).html', event_data['product'])
                    if event_data['product']:
                        event_data['product'] = event_data['product'][0]

            elif k.startswith('SA'):
                event_data[k[2:].lower()] = request.GET[k]

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
            'store_type': 'Shopify',
            'plan': plan.title,
            'plan_id': plan.id,
            'affiliate': affiliate if not disable_affiliate else 'disables',
            'sub_user': request.user.is_subuser,
            'extension_version': request.user.get_config('extension_version'),
            'total': order_data['total'],
            'quantity': order_data['quantity'],
            'cart': 'SACart' in request.GET
        })

        if not settings.DEBUG:
            keen_order_event.delay("auto_fulfill", event_data)

        cache.set(event_key, True, timeout=3600)

    return HttpResponseRedirect(redirect_url)


@login_required
def locate(request, what):
    if what == 'order':
        aliexpress_id = safe_int(request.GET.get('aliexpress'))

        if aliexpress_id:
            track = ShopifyOrderTrack.objects.filter(user=request.user.models_user, source_id=aliexpress_id).first()
            if track:
                return HttpResponseRedirect(
                    '{}?store={}&query_order={}&new=1&status=any&'
                    'financial=any&fulfillment=any&awaiting_order=false&connected=false'.format(
                        reverse('orders'), track.store.id, aliexpress_id))

            track = CommerceHQOrderTrack.objects.filter(user=request.user.models_user, source_id=aliexpress_id).first()
            if track:
                return HttpResponseRedirect(
                    '{}?store={}&query={}'.format(reverse('chq:orders_list'), track.store.id, aliexpress_id))

    elif what == 'product':
        if request.GET.get('shop') and request.GET.get('id'):
            store = utils.get_store_from_request(request)
            product = store.shopifyproduct_set.filter(shopify_id=request.GET.get('id')).first() if store else None
            if product:
                return HttpResponseRedirect(reverse('product_view', kwargs={'pid': product.id}))

    raise Http404


@login_required
def product_alerts(request):
    store = utils.get_store_from_request(request)
    if not store:
        return HttpResponseRedirect(reverse('goto-page', kwargs={'url_name': 'product_alerts'}))

    if not request.user.can('price_changes.use'):
        return render(request, 'product_alerts.html', {
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
        product = get_object_or_404(ShopifyProduct, id=product)
        permissions.user_can_view(request.user, product)

    post_per_page = settings.ITEMS_PER_PAGE
    page = safe_int(request.GET.get('page'), 1)

    changes = using_replica(ProductChange, request.GET.get('rep')).select_related('shopify_product') \
        .select_related('shopify_product__default_supplier') \
        .filter(user=request.user.models_user, shopify_product__store=store)

    if request.user.is_subuser:
        store_ids = request.user.profile.subuser_permissions.filter(
            codename='view_alerts'
        ).values_list(
            'store_id', flat=True
        )
        changes = changes.filter(shopify_product__store_id__in=store_ids)

    if product:
        changes = changes.filter(shopify_product=product)
    else:
        changes = changes.filter(hidden=show_hidden)

    category = request.GET.get('category')
    if category:
        changes = changes.filter(categories__icontains=category)
    product_type = request.GET.get('product_type', '')
    if product_type:
        changes = changes.filter(shopify_product__product_type__icontains=product_type)

    changes = changes.order_by('-updated_at')

    paginator = InfinitePaginator(changes, post_per_page)
    page = paginator.page(page)
    changes = page.object_list

    products = []
    product_variants = {}
    for i in changes:
        shopify_id = i.product.get_shopify_id()
        if shopify_id and str(shopify_id) not in products:
            products.append(str(shopify_id))
    try:
        if len(products):
            products = utils.get_shopify_products(store=store, product_ids=products, fields='id,title,variants')
            for p in products:
                product_variants[str(p['id'])] = p['variants']
    except:
        capture_exception()

    inventory_item_ids = []
    for i in changes:
        changes_map = i.get_changes_map(category)
        variants = product_variants.get(str(i.product.get_shopify_id()), None)
        if variants is not None:
            for c in changes_map['variants']['quantity']:
                index = variant_index_from_supplier_sku(i.product, c['sku'], variants)
                if index is not None:
                    inventory_item_id = variants[index]['inventory_item_id']
                    if variants[index]['inventory_management'] == 'shopify' and inventory_item_id not in inventory_item_ids:
                        inventory_item_ids.append(inventory_item_id)

    variant_quantities = {}
    if len(inventory_item_ids) > 0:
        inventories = utils.get_shopify_inventories(store, inventory_item_ids)
        for inventory in inventories:
            variant_quantities[str(inventory['inventory_item_id'])] = inventory['available']

    product_changes = []
    for i in changes:
        change = {
            'qelem': i,
            'id': i.id,
            'data': i.get_data(),
            'changes': i.get_changes_map(category),
            'product': i.product,
            'shopify_link': i.product.shopify_link(),
            'original_link': i.product.get_original_info().get('url')
        }

        variants = product_variants.get(str(i.product.get_shopify_id()), None)
        for c in change['changes']['variants']['quantity']:
            if variants is not None:
                index = variant_index_from_supplier_sku(i.product, c['sku'], variants)
                if index is not None:
                    if variants[index]['inventory_management'] == 'shopify':
                        quantity = variant_quantities.get(str(variants[index]['inventory_item_id']), None)
                        c['shopify_value'] = quantity
                    else:
                        c['shopify_value'] = "Unmanaged"
                else:
                    c['shopify_value'] = "Not Found"
            else:
                c['shopify_value'] = "Not Found"
        for c in change['changes']['variants']['price']:
            if variants is not None:
                index = variant_index_from_supplier_sku(i.product, c['sku'], variants)
                if index is not None:
                    c['shopify_value'] = variants[index]['price']
                else:
                    c['shopify_value_label'] = "Not Found"
            else:
                c['shopify_value_label'] = "Not Found"

        product_changes.append(change)

    # Allow sending notification for new changes
    cache.delete('product_change_%d' % request.user.models_user.id)

    # Delete sidebar alert info cache
    cache.delete(make_template_fragment_key('alert_info', [request.user.id]))

    return render(request, 'product_alerts.html', {
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


@login_required
def bundles_bonus(request, bundle_id):
    bundle = get_object_or_404(FeatureBundle, register_hash=bundle_id)
    if request.method == 'POST':
        form = EmailForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data['email']
            reg = utils.generate_plan_registration(plan=None, bundle=bundle, data={'email': email})

            try:
                user = User.objects.get(email__iexact=email)
                user.profile.bundles.add(bundle)

                reg.expired = True
            except User.DoesNotExist:
                pass

            reg.save()

            messages.success(request, f'Bundle {bundle.title} has been added to your account.')
            return HttpResponseRedirect('/')

    else:
        initial = {}

        if request.user.is_authenticated:
            initial = {'email': request.user.email}

        form = RegisterForm(initial=initial)

    return render(request, "bundles_bonus.html", {
        'form': form,
        'bundle': bundle
    })


@login_required
def products_collections(request, collection):
    if not request.user.can('us_products.use'):
        raise PermissionDenied()

    # force use new layout
    # TODO: remove later
    request.session['old_layout'] = False

    aliexpress_categories = json.load(open(settings.ALIEXPRESS_CATEGORIES_PATH))

    return render(request, 'products_collections.html', {
        'aliexpress_categories': aliexpress_categories,
        'breadcrumbs': ['Products', 'Collections', {'title': 'US', 'url': request.path}]
    })


@login_required
def logout(request):
    user_logout(request)
    return redirect('index')


def register(request, registration=None, subscribe_plan=None):
    if request.user.is_authenticated and not request.user.is_superuser:
        messages.warning(request, 'You are already logged in')
        return HttpResponseRedirect('/')

    funnel_url = 'https://www.dropified.com/pricing'
    if request.method == 'GET' and not request.GET and request.path == '/accounts/register':
        return HttpResponseRedirect(funnel_url)

    email = request.GET.get('email', '')
    if email:
        if '@' not in email:
            email = decode_params(email)
        else:
            # Base64 encode the email in url
            params = request.GET.copy()
            params['email'] = encode_params(email)

            return HttpResponseRedirect('{}?{}'.format(request.path, params.urlencode()))

    try_plan = registration and registration.endswith('-try')
    if registration and (registration.endswith('-subscribe') or try_plan):
        slug = registration.replace('-subscribe', '').replace('-try', '')
        subscribe_plan = get_object_or_404(GroupPlan, slug=slug, payment_gateway='stripe')
        if not subscribe_plan.is_stripe():
            raise Http404('Not a Stripe Plan')
        elif subscribe_plan.locked:
            try:
                assert request.GET.get('l') and request.GET.get('l') in subscribe_plan.register_hash
            except:
                capture_exception(level='warning')
                return HttpResponseRedirect(funnel_url)

        registration = None

    if registration:
        # Convert the hash to a PlanRegistration model
        registration = get_object_or_404(PlanRegistration, register_hash=registration)

        if registration.expired:
            if request.user.is_superuser:
                messages.error(request, 'Registration link <i>{}</i> is expired'.format(registration.register_hash))

            return HttpResponseRedirect('/')

    if request.method == 'POST':
        form = RegisterForm(request.POST)
        form.set_plan_registration(registration)

        if form.is_valid():

            if registration and registration.plan:
                # do not autoprofile, to not fire Stripe webhooks
                new_user = form.save(False)
                new_user.no_auto_profile = True
                new_user.save()
                profile = UserProfile.objects.create(user=new_user, plan=registration.plan)
                if profile.plan.is_stripe():
                    profile.apply_subscription(profile.plan)
            else:
                new_user = form.save()

            new_user.set_config('_tos-accept', True)

            reg_coupon = request.GET.get('cp')
            if reg_coupon:
                new_user.set_config('registration_discount', Signer().unsign(base64_decode(reg_coupon)))

            if subscribe_plan:
                try:
                    if try_plan:
                        new_user.set_config('try_plan', True)
                    else:
                        new_user.stripe_customer.can_trial = False
                        new_user.stripe_customer.save()

                except:
                    capture_exception()

            elif registration is None or registration.get_usage_count() is None:
                utils.apply_plan_registrations(form.cleaned_data['email'])
            else:
                utils.apply_shared_registration(new_user, registration)

            new_user = authenticate(username=new_user.username, password=form.cleaned_data['password1'])

            login(request, new_user)

            RegistrationEvent.objects.create(user=request.user)

            if subscribe_plan:
                if not try_plan and not subscribe_plan.is_free:
                    return HttpResponseRedirect("/user/profile?auto={}#billing".format(subscribe_plan.id))
                elif try_plan and not subscribe_plan.is_free:
                    return HttpResponseRedirect("/user/profile?try={}#plan".format(subscribe_plan.id))

            return HttpResponseRedirect("/")

    else:
        try:

            initial = {
                'email': (registration.email if registration else email).strip(),
                'fullname': (request.GET.get('name', '')).strip(),
            }
        except:
            initial = {}

        form = RegisterForm(initial=initial)

    if registration and registration.email:
        form.fields['email'].widget.attrs['readonly'] = True

    reg_coupon = request.GET.get('cp')
    if reg_coupon:
        try:
            reg_coupon = Signer().unsign(base64_decode(reg_coupon))
            reg_coupon = stripe.Coupon.retrieve(reg_coupon)
            if not reg_coupon.valid:
                reg_coupon = None
            else:
                try:
                    reg_coupon = reg_coupon.metadata.msg
                except:
                    reg_coupon = f'Using {reg_coupon.id} Coupon'
        except:
            reg_coupon = None
            capture_exception()

        if not reg_coupon:
            raise Http404('Coupon Not Found')

    return render(request, "registration/register.html", {
        'form': form,
        'registration': registration,
        'subscribe_plan': subscribe_plan,
        'reg_coupon': reg_coupon,
    })


def sudo_login(request):
    if request.GET.get('token'):
        token = request.GET.get('token')

        data = jwt_decode(token)
        if not request.user.is_authenticated:
            return redirect('%s?next=%s%%3F%s' % (settings.LOGIN_URL, request.path, quote_plus(request.GET.urlencode())))

        target_user = User.objects.get(id=data['id'])

        AdminEvent.objects.create(
            user=request.user,
            event_type='login_as_user',
            target_user=target_user,
            data=json.dumps({'token': token}))

        hijacker = request.user
        hijack_history = [request.user._meta.pk.value_to_string(hijacker)]
        if request.session.get('hijack_history'):
            hijack_history = request.session['hijack_history'] + hijack_history

        target_user.backend = settings.AUTHENTICATION_BACKENDS[0]
        login(request, target_user)

        request.session['hijack_history'] = hijack_history
        request.session['is_hijacked_user'] = True
        request.session['display_hijack_warning'] = True
        request.session.modified = True

        return redirect('index')

    target_user = None
    if request.session.get('sudo_user'):
        target_user = User.objects.get(id=request.session['sudo_user'])
    elif request.GET.get('email'):
        target_user = User.objects.get(email__iexact=request.GET['email'])

    return LoginView.as_view(
        authentication_form=EmailAuthenticationForm,
        extra_context={
            'target_user': target_user
        }
    )(request)


def account_password_setup(request, register_id):
    errors = []
    registration = get_object_or_404(AccountRegistration, register_hash=register_id, expired=False)

    if request.method == 'POST':

        new_password1 = request.POST.get('new_password1')
        new_password2 = request.POST.get('new_password2')

        if not new_password1 or not new_password2:
            errors.append('Password or Password verification is empty')
        elif new_password1 != new_password2:
            errors.append('Password and Password verification do not match')
        else:
            try:
                validate_password(new_password1, user=registration.user)
            except ValidationError as e:
                for error in e.error_list:
                    for message in error.messages:
                        errors.append(message)

            if not errors:
                registration.user.set_password(new_password1)
                registration.user.save()

                registration.expired = True
                registration.save()

                registration.user.backend = settings.AUTHENTICATION_BACKENDS[0]
                login(request, registration.user)
                request.user = registration.user

                messages.success(request, 'Your password has been changed successfully')

                return HttpResponseRedirect('/')

    return render(request, "registration/password_setup.html", {
        'registration': registration,
        'errors': errors
    })


@xframe_options_exempt
@csrf_protect
def user_login_view(request):
    if request.method == 'GET':
        request.session['use_login_captcha'] = page_rpm_counter('login') > 20

    return LoginView.as_view(authentication_form=EmailAuthenticationForm)(request)


@require_http_methods(['GET'])
@login_required
def user_profile_invoices(request):
    if request.is_ajax() and request.user.have_stripe_billing():
        invoices = get_stripe_invoice_list(request.user.stripe_customer)
        return render(request, 'payments/invoice_table.html', {'invoices': invoices})
    raise Http404


@login_required
def user_invoices(request, invoice_id):
    if not request.user.have_stripe_billing():
        raise Http404

    invoice = get_stripe_invoice(invoice_id, expand=['charge'])

    if not invoice:
        raise Http404
    if not invoice.customer == request.user.stripe_customer.customer_id:
        raise Http404

    return render(request, 'user/invoice_view.html', {'invoice': invoice})


@login_required
def user_invoices_download(request, invoice_id):
    if not request.user.have_stripe_billing():
        raise Http404

    invoice = get_stripe_invoice(invoice_id, expand=['charge'])

    if not invoice:
        raise Http404
    if not invoice.customer == request.user.stripe_customer.customer_id:
        raise Http404

    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = 'attachment; filename="%s.pdf"' % invoice.id
    buffer = io.BytesIO()  # Output buffer
    draw_pdf(buffer, invoice)
    response.write(buffer.getvalue())
    buffer.close()

    return response


def update_layout(request):
    old_layout = request.session.get('old_layout')
    request.session['old_layout'] = not old_layout
    referer = request.META.get('HTTP_REFERER')
    if not referer or 'update-layout' in referer:
        referer = 'index'
    return redirect(referer)
