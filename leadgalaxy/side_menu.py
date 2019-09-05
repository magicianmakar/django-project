import re
from django.conf import settings
from django.urls import reverse_lazy
from django.core.urlresolvers import resolve


def get_menu_structure(namespace):
    body = []

    if namespace == '':
        # Shopify
        body = [
            ('orders', ['place-orders', 'tracking']),
            ('all-products', [
                'non-connected',
                'import-products',
                'boards',
                'alerts',
            ]),
            ('business', [
                'profit-dashboard',
                'marketing-feeds',
                'subusers',
                'callflex',
                'tubehunt',
                'us-product-database',
                'tools',
            ]),
        ]

    elif namespace == 'chq':
        # CHQ
        body = [
            ('orders', ['place-orders', 'tracking']),
            ('all-products', [
                'non-connected',
                'import-products',
                'boards',
                'alerts',
            ]),
            ('business', [
                'marketing-feeds',
                'subusers',
                'callflex',
                'tubehunt',
                'us-product-database',
                'tools',
            ]),
        ]

    elif namespace == 'gear':
        # GearBubble
        body = [
            ('orders', ['place-orders', 'tracking']),
            ('all-products', [
                'non-connected',
                'import-products',
                'boards',
            ]),
            ('business', [
                'marketing-feeds',
                'subusers',
                'callflex',
                'tubehunt',
                'us-product-database',
                'tools',
            ]),
        ]

    elif namespace == 'gkart':
        # GrooveKart
        body = [
            ('orders', ['place-orders', 'tracking']),
            ('all-products', [
                'non-connected',
                'import-products',
                'boards',
                'alerts',
            ]),
            ('business', [
                'marketing-feeds',
                'subusers',
                'callflex',
                'tubehunt',
                'us-product-database',
                'tools',
            ]),
        ]

    elif namespace == 'woo':
        # WooCommerce
        body = [
            ('orders', ['place-orders', 'tracking']),
            ('all-products', [
                'non-connected',
                'import-products',
                'boards',
            ]),
            ('business', [
                'marketing-feeds',
                'subusers',
                'callflex',
                'tubehunt',
                'us-product-database',
                'tools',
            ]),
        ]

    header = [
        ('get-started', ['get-started']),
    ]

    footer = [
        ('help', ['help']),
        ('settings', ['settings']),
    ]

    named = [
        ('account', ['account']),
        ('academy', ['academy']),
        ('video_training', ['video_training']),
    ]

    return {'body': body, 'header': header, 'footer': footer, 'named': named}


def get_menu_item_data():
    return {
        'orders': {
            'title': 'Orders',
            'icon': get_static('vector-orders.svg'),
            'classes': '',
            'url': '',
            'permissions': ['orders.view'],
        },
        'place-orders': {
            'title': 'Place Orders',
            'classes': '',
            'url': None,
            'url_name': 'orders_list',
            'url_args': None,
            'url_kwargs': None,
            'permissions': ['orders.view'],
            'match': re.compile(r'(/\w+)?/orders$'),
        },
        'tracking': {
            'title': 'Tracking',
            'classes': '',
            'url': None,
            'url_name': 'orders_track',
            'url_args': None,
            'url_kwargs': None,
            'permissions': ['orders.view'],
            'match': re.compile(r'(/\w+)?/orders/track'),
        },
        'all-products': {
            'title': 'All Products',
            'icon': get_static('vector-products.svg'),
            'classes': '',
            'url': '',
            'permissions': [],
        },
        'non-connected': {
            'title': 'Non Connected',
            'classes': '',
            'url': None,
            'url_name': 'products_list',
            'url_args': None,
            'url_kwargs': None,
            'permissions': [],
            'match': re.compile(r'(/\w+)?/products?$'),
        },
        'import-products': {
            'title': 'Import Products',
            'classes': '',
            'url': None,
            'url_name': 'article-content-page',
            'url_args': None,
            'url_kwargs': {"slug_article": "source-import-products"},
            'permissions': [],
            'match': re.compile(r'(/\w+)?/pages/content/source-import-products'),
        },
        'boards': {
            'title': 'Boards',
            'classes': '',
            'url': None,
            'url_name': 'boards_list',
            'url_args': None,
            'url_kwargs': None,
            'permissions': ['view_product_boards.sub'],
            'match': re.compile(r'(/\w+)?/boards/list'),
        },
        'alerts': {
            'title': 'Alerts',
            'classes': '',
            'url': None,
            'url_name': 'product_alerts',
            'url_args': None,
            'url_kwargs': None,
            'permissions': ['price_changes.use'],
            'match': re.compile(r'(/\w+)?/products/update'),
        },
        'business': {
            'title': 'Business',
            'icon': get_static('vector-business.svg'),
            'classes': '',
            'url': '',
            'permissions': [],
            'match': re.compile(r'$'),
        },
        'profit-dashboard': {
            'title': 'Profit Dashboard',
            'classes': '',
            'url': None,
            'url_name': 'profit_dashboard.views.index',
            'url_args': None,
            'url_kwargs': None,
            'permissions': ['profit_dashboard.view'],
            'match': re.compile(r'(/\w+)?/profit-dashboard'),
        },
        'callflex': {
            'title': 'CallFlex',
            'classes': '',
            'url': None,
            'url_name': 'phone_automation_index',
            'url_args': None,
            'url_kwargs': None,
            'permissions': [],
            'match': re.compile(r'(/\w+)?/callflex'),
        },
        'marketing-feeds': {
            'title': 'Marketing Feeds',
            'classes': '',
            'url': None,
            'url_name': 'product_feeds',
            'url_args': None,
            'url_kwargs': None,
            'permissions': [],
            'match': re.compile(r'(/\w+)?/marketing/feeds'),
        },
        'tubehunt': {
            'title': 'TubeHunt',
            'classes': '',
            'url': None,
            'url_name': 'youtube_ads.views.index',
            'url_args': None,
            'url_kwargs': None,
            'permissions': [],
            'match': re.compile(r'(/\w+)?/tubehunt'),
        },
        'us-product-database': {
            'title': 'US Products',
            'classes': '',
            'url': None,
            'url_name': 'products_collections',
            'url_args': None,
            'url_kwargs': {'collection': 'us'},
            'permissions': [],
            'match': re.compile(r'/products/collections/\w+'),
        },
        'subusers': {
            'title': 'Sub Users',
            'classes': '',
            'url': None,
            'url_name': 'subusers',
            'url_args': None,
            'url_kwargs': None,
            'permissions': ['sub_users.use'],
            'match': re.compile(r'(/\w+)?/subusers'),
        },
        'tools': {
            'title': 'Tools',
            'classes': '',
            'url': None,
            'url_name': 'article-content-page',
            'url_args': None,
            'url_kwargs': {"slug_article": "tools-business-tools"},
            'permissions': [],
            'match': re.compile(r'(/\w+)?/pages/content/tools-business-tools'),
        },
        'academy': {
            'title': 'Dropified <span id="academy-span">Academy</span>',
            'classes': '',
            'url': 'https://academy.dropified.com/',
            'url_name': None,
            'url_args': None,
            'url_kwargs': None,
            'permissions': [],
            'match': re.compile(r'$'),
        },
        'video_training': {
            'title': 'Video Training',
            'classes': '',
            'url': 'https://academy.dropified.com/training/',
            'permissions': [],
            'match': re.compile(r'$'),
        },
        'account': {
            'title': 'Manage Account',
            'classes': '',
            'url': None,
            'url_name': 'user_profile',
            'url_args': None,
            'url_kwargs': None,
            'permissions': [],
            'match': re.compile(r'(/\w+)?/user/profile'),
        },
        'help': {
            'title': 'Get Support',
            'classes': '',
            'url': 'https://help.dropified.com/',
            'url_name': None,
            'url_args': None,
            'url_kwargs': None,
            'permissions': [],
            'match': re.compile(r'$'),
        },
        'settings': {
            'title': 'Settings',
            'classes': '',
            'url': None,
            'url_name': 'settings',
            'url_args': None,
            'url_kwargs': None,
            'permissions': [],
            'match': re.compile(r'(/\w+)?/settings'),
            'is_ns_aware': False,
        },
        'get-started': {
            'title': 'Get Started',
            'classes': '',
            'url': None,
            'url_name': 'index',
            'url_args': None,
            'url_kwargs': None,
            'permissions': [],
            'match': re.compile(r'(/\w+)?/$'),
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

    menu = []
    for section_key, item_keys in menu_structure:
        section = menu_data[section_key]
        items = []
        for item_key in item_keys:
            item = menu_data[item_key]

            if any([not has_perm(p) for p in item['permissions']]):
                # User doesn't have the permission to access this resource.
                continue

            check_active = item['match']
            if check_active.match(request_path):
                item['classes'] = 'active'

            item['url'] = create_url(item, namespace)
            items.append(item)

        if not items:
            # Empty section! There is no need to add this section.
            continue

        section['items'] = items
        section['url'] = items[0]['url']
        section['classes'] = items[0]['classes']
        menu.append(section)

    return menu


def create_named_menu(menu_structure, menu_data, request, namespace):
    raw = create_menu(menu_structure, menu_data, request, namespace)
    menu = {}
    for name, item in zip(menu_structure, raw):
        menu[name[0]] = dict(
            title=item['title'],
            classes=item['classes'],
            url=item['url'],
        )

    return menu


def create_url(item, namespace):
    if item['url']:
        return item['url']

    url_name = item['url_name']
    args = item['url_args'] or tuple()
    kwargs = item['url_kwargs'] or {}

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

    return url_name


def get_static(path):
    return f"{settings.STATIC_URL}{path}"


def get_active_item(request_path):
    for item in get_menu_item_data().values():
        check_active = item.get('match')
        if check_active and check_active.match(request_path):
            return item


def get_namespace(request):
    request_path = request.path

    item = get_active_item(request_path)
    url_obj = resolve(request_path)

    namespace = url_obj.namespace
    url_name = url_obj.url_name

    if url_name == 'product_feeds':
        namespace = url_obj.kwargs.get('store_type', '') or ''

    if item and item.get('is_ns_aware', True):
        request.session["nav_ns"] = namespace
    else:
        namespace = request.session.get("nav_ns", "")

    return namespace
