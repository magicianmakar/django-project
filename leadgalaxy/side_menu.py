import re
from django.conf import settings
from django.urls import reverse_lazy
from django.urls import resolve


def get_menu_structure(namespace, request):
    body = [
        ('products', [
            'all-products',
            'prints',
            'boards',
            'alerts',
            'us-product-database',
            'import-products',
            'alibaba-products'
        ]),
        ('orders', ['place-orders', 'tracking']),
        ('business', [
            'profit-dashboard',
            'marketing-feeds',
            'subusers',
            'callflex',
            'tubehunt',
            'tools',
        ]),
    ]

    header = [
        ('get-started', ['get-started']),
        ('settings', ['settings']),
    ]

    footer = [
        ('help', ['help']),
    ]

    if request.user.profile.plan.is_plod:
        footer.append(('plod_help', ['plod_help']))

    named = [
        ('account', ['account']),
    ]

    return {'body': body, 'header': header, 'footer': footer, 'named': named}


def get_menu_item_data(request):
    """
    Entry structure:
        'title': 'Place Orders',
        'classes': '',
        'url': None,
        'url_name': 'orders_list',
        'url_args': None,
        'url_kwargs': None,
        'permissions': ['orders.view'],
        'match': re.compile(r'/orders$'),
    - title: Text of link.
    - classes: The classes applied when active
    - url: URL in string
    - url_name: Name in Django.
    - url_args: Args to reverse
    - url_kwargs: kwargs to reverse
    - permission: Will be used user.can
    - match: Will be used to apply classes.
    - platforms: Only show on the specified platforms (ex: Shopify, chq, gkart...)
    """
    return {
        'orders': {
            'title': 'Orders',
            'icon': get_static('vector-orders.svg'),
            'permissions': ['orders.view'],
        },
        'place-orders': {
            'title': 'Place Orders',
            'url_name': 'orders_list',
            'permissions': ['orders.view'],
            'match': re.compile(r'(/\w+)?/orders$'),
        },
        'tracking': {
            'title': 'Tracking',
            'url_name': 'orders_track',
            'permissions': ['orders.view'],
            'match': re.compile(r'(/\w+)?/orders/track'),
        },
        'products': {
            'title': 'Products',
            'icon': get_static('vector-products.svg'),
        },
        'all-products': {
            'title': 'Saved Products',
            'url_name': 'products_list',
            'match': re.compile(r'(/chq|/gear|/gkart|/woo|/bigcommerce)?/products$'),
        },
        'import-products': {
            'title': 'Import Products',
            'url_name': 'article-content-page',
            'url_kwargs': {"slug_article": "source-import-products"},
            'permissions': ["import_list.use"],
            'match': re.compile(r'(/\w+)?/pages/content/source-import-products'),
        },
        'alibaba-products': {
            'title': 'Alibaba Products',
            'url_name': 'alibaba:products',
            'permissions': ['alibaba_integration.use'],
            'match': re.compile(r'(/\w+)?/alibaba/products'),
            'is_ns_aware': False,
        },
        'boards': {
            'title': 'Boards',
            'url_name': 'boards_list',
            'permissions': ['view_product_boards.use', 'view_product_boards.sub'],
            'match': re.compile(r'(/\w+)?/boards/list'),
        },
        'alerts': {
            'title': 'Alerts',
            'url_name': 'product_alerts',
            'permissions': ['price_changes.use', 'price_change_options.use'],
            'match': re.compile(r'(/\w+)?/products/update'),
            'platforms': ['shopify', 'chq', 'woo', 'gkart', 'bigcommerce']
        },
        'business': {
            'title': 'Business',
            'icon': get_static('vector-business.svg'),
        },
        'profit-dashboard': {
            'title': 'Profit Dashboard',
            'url_name': 'profit_dashboard.views.index',
            'permissions': ['profit_dashboard.view'],
            'match': re.compile(r'(/\w+)?/profit-dashboard'),
            'platforms': ['shopify', 'gkart', 'bigcommerce', 'woo', 'chq']
        },
        'callflex': {
            'title': 'CallFlex',
            'url_name': 'phone_automation_index',
            'match': re.compile(r'(/\w+)?/callflex'),
            'permissions': ['phone_automation.use'],
            'is_ns_aware': False,
        },
        'marketing-feeds': {
            'title': 'Marketing Feeds',
            'url_name': 'product_feeds',
            'permissions': ['product_feeds.use', 'google_product_feed.use'],
            'match': re.compile(r'(/\w+)?/marketing/feeds'),
        },
        'tubehunt': {
            'title': 'TubeHunt',
            'url_name': 'youtube_ads.views.index',
            'permissions': ['youtube_ads.use'],
            'match': re.compile(r'(/\w+)?/tubehunt'),
            'is_ns_aware': False,
        },
        'us-product-database': {
            'title': 'US Products',
            'url_name': 'products_collections',
            'permissions': ['us_products.use'],
            'url_kwargs': {'collection': 'us'},
            'match': re.compile(r'/products/collections/\w+'),
        },
        'subusers': {
            'title': 'Sub Users',
            'url_name': 'subusers',
            'permissions': ['sub_users.use'],
            'match': re.compile(r'(/\w+)?/subusers'),
        },
        'tools': {
            'title': 'Tools',
            'url_name': 'article-content-page',
            'url_kwargs': {"slug_article": "tools-business-tools"},
            'permissions': ['businesstools_page.use'],
            'match': re.compile(r'(/\w+)?/pages/content/tools-business-tools'),
        },
        'academy': {
            'title': '<span id="academy-span">Dropshipping 101</span>',
            'url': 'https://academy.dropified.com/',
        },
        'video_training': {
            'title': 'Video Training',
            'url': 'https://academy.dropified.com/training/',
        },
        'account': {
            'title': 'Manage Account',
            'url_name': 'user_profile',
            'match': re.compile(r'(/\w+)?/user/profile'),
        },
        'help': {
            'title': f'{"Dropified " if request.user.profile.plan.is_plod else ""}Help Center',
            'url': 'https://learn.dropified.com/',
        },
        'plod_help': {
            'title': 'PLOD Help Center',
            'url': 'https://plod.dropified.com/',
        },
        'settings': {
            'title': 'Settings',
            'url_name': 'settings',
            'match': re.compile(r'(/\w+)?/settings'),
            'is_ns_aware': False,
        },
        'get-started': {
            'title': 'Home',
            'url_name': 'index',
            'match': re.compile(r'(/chq|/gear|/gkart|/woo|/bigcommerce)?/$'),
        },
        'prints': {
            'title': 'Print On Demand',
            'url_name': 'prints:index',
            'match': re.compile(r'^/print-on-demand'),
            'is_ns_aware': False,
            'permissions': ['print_on_demand.use'],
        },
        'dropified-product': {
            'title': 'Fulfilled by Dropified',
            'url_name': 'dropified_product:index',
            'match': re.compile(r'^/dropified_product'),
            'is_ns_aware': False,
            'permissions': ['dropified_product.use'],
        },
    }


def create_menu(menu_structure, menu_data, request, namespace):
    request_path = request.path
    user = request.user
    is_anonymous = user.is_anonymous

    def has_perm(perm):
        if is_anonymous:
            return False

        return user.can(perm)

    # Know which bypass instead of removing these permissions from menu
    upsell_permission_exceptions = ['price_changes.use', 'profit_dashboard.view',
                                    'mapping_bundle.use', 'suppliers_shipping_mapping.use', 'sub_users.use']
    menu = []
    for section_key, item_keys in menu_structure:
        section = menu_data[section_key]
        items = []
        for item_key in item_keys:
            item = menu_data[item_key]

            if type(item.get('permissions')) is not bool:
                permissions = [p for p in item.get('permissions', []) if p not in upsell_permission_exceptions]
                allowed_permissions = [has_perm(p) for p in permissions]
                if len(allowed_permissions) > 0 and not any(allowed_permissions):
                    # User doesn't have any of the permissions to access this resource.
                    continue
            else:
                if not item['permissions']:
                    continue

            if item.get('platforms'):
                search_ns = namespace if namespace else 'shopify'
                if search_ns not in item['platforms']:
                    continue

            check_active = item.get('match')
            if check_active and check_active.match(request_path):
                item['classes'] = 'active'

            item['url'] = create_url(item, namespace)
            items.append(item)

        if not items:
            # Empty section! There is no need to add this section.
            continue

        section['items'] = items
        section['url'] = items[0]['url']
        section['classes'] = items[0].get('classes', '')
        menu.append(section)

    return menu


def create_named_menu(menu_structure, menu_data, request, namespace):
    raw = create_menu(menu_structure, menu_data, request, namespace)
    menu = {}
    for name, item in zip(menu_structure, raw):
        menu[name[0]] = dict(
            title=item['title'],
            classes=item.get('classes', ''),
            url=create_url(item, namespace),
        )

    return menu


def create_url(item, namespace):
    if item.get('url'):
        return item['url']

    url_name = item['url_name']
    args = item.get('url_args', tuple())
    kwargs = item.get('url_kwargs', {})

    url_name = fix_url_name(url_name, namespace)

    if url_name == 'product_feeds':
        if namespace:
            kwargs['store_type'] = namespace

    elif item.get('is_ns_aware', True) and namespace:
        # Add namespace
        url_name = f"{namespace}:{url_name}"

    return reverse_lazy(url_name, args=args, kwargs=kwargs)


def fix_url_name(url_name, namespace):
    """
    This function takes care of the differences between url names of different
    stores. Ideally, orders list page should be named orders_list for all store
    types.
    """

    if url_name == 'orders_list' and not namespace:
        url_name = 'orders'
    elif url_name == 'products_list' and not namespace:
        url_name = 'product'
    elif url_name == 'profit_dashboard.views.index' and namespace:
        url_name = 'profits'

    return url_name


def get_static(path):
    return f"{settings.STATIC_URL}{path}"


def get_active_item(request):
    for item in get_menu_item_data(request).values():
        check_active = item.get('match')
        if check_active and check_active.match(request.path):
            return item


def get_namespace(request):
    item = get_active_item(request)
    url_obj = resolve(request.path)

    namespace = url_obj.namespace
    url_name = url_obj.url_name

    if url_name == 'product_feeds':
        namespace = url_obj.kwargs.get('store_type', '') or ''

    if item and item.get('is_ns_aware', True):
        request.session["nav_ns"] = namespace
    else:
        namespace = request.session.get("nav_ns", "")

    return namespace
