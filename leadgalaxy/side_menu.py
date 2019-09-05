import re
from django.conf import settings
from django.urls import reverse


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


def get_menu_item_data(namespace):
    get_url = create_get_url(namespace)

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
            'url': get_url('orders_list'),
            'permissions': ['orders.view'],
            'match': re.compile(r'(/\w+)?/orders$'),
        },
        'tracking': {
            'title': 'Tracking',
            'classes': '',
            'url': get_url('orders_track'),
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
            'url': get_url('products_list'),
            'permissions': [],
            'match': re.compile(r'(/\w+)?/products?$'),
        },
        'import-products': {
            'title': 'Import Products',
            'classes': '',
            'url': get_url(
                'article-content-page',
                slug_article='source-import-products',
            ),
            'permissions': [],
            'match': re.compile(r'(/\w+)?/pages/content/source-import-products'),
        },
        'boards': {
            'title': 'Boards',
            'classes': '',
            'url': get_url('boards_list'),
            'permissions': ['view_product_boards.sub'],
            'match': re.compile(r'(/\w+)?/boards/list'),
        },
        'alerts': {
            'title': 'Alerts',
            'classes': '',
            'url': get_url('product_alerts'),
            'permissions': ['price_changes.use'],
            'match': re.compile(r'(/\w+)?/products/update'),
        },
        'business': {
            'title': 'Business',
            'icon': get_static('vector-business.svg'),
            'classes': '',
            'url': '',
            'permissions': [],
            'match': re.compile(r''),
        },
        'profit-dashboard': {
            'title': 'Profit Dashboard',
            'classes': '',
            'url': get_url('profit_dashboard.views.index'),
            'permissions': ['profit_dashboard.view'],
            'match': re.compile(r'(/\w+)?/profit-dashboard'),
        },
        'callflex': {
            'title': 'CallFlex',
            'classes': '',
            'url': get_url('phone_automation_index'),
            'permissions': [],
            'match': re.compile(r'(/\w+)?/callflex'),
        },
        'marketing-feeds': {
            'title': 'Marketing Feeds',
            'classes': '',
            'url': get_url('product_feeds'),
            'permissions': [],
            'match': re.compile(r'(/\w+)?/marketing/feeds'),
        },
        'tubehunt': {
            'title': 'TubeHunt',
            'classes': '',
            'url': get_url('youtube_ads.views.index'),
            'permissions': [],
            'match': re.compile(r'(/\w+)?/tubehunt'),
        },
        'us-product-database': {
            'title': 'US Products',
            'classes': '',
            'url': get_url('products_collections', collection='us'),
            'permissions': [],
            'match': re.compile(r'/products/collections/\w+'),
        },
        'subusers': {
            'title': 'Sub Users',
            'classes': '',
            'url': get_url('subusers'),
            'permissions': ['sub_users.use'],
            'match': re.compile(r'(/\w+)?/subusers'),
        },
        'tools': {
            'title': 'Tools',
            'classes': '',
            'url': get_url('article-content-page',
                           slug_article='tools-business-tools'),
            'permissions': [],
            'match': re.compile(r'(/\w+)?/pages/content/tools-business-tools'),
        },
        'academy': {
            'title': 'Dropified <span id="academy-span">Academy</span>',
            'classes': '',
            'url': 'https://academy.dropified.com/',
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
            'url': get_url('user_profile')() + '#plan',
            'permissions': [],
            'match': re.compile(r'(/\w+)?/user/profile'),
        },
        'help': {
            'title': 'Get Support',
            'classes': '',
            'url': 'https://help.dropified.com/',
            'permissions': [],
            'match': re.compile(r'$'),
        },
        'settings': {
            'title': 'Settings',
            'classes': '',
            'url': get_url('settings'),
            'permissions': [],
            'match': re.compile(r'(/\w+)?/settings'),
        },
        'get-started': {
            'title': 'Get Started',
            'classes': '',
            'url': get_url('index'),
            'permissions': [],
            'match': re.compile(r'(/\w+)?/$'),
        },
    }


def create_menu(menu_structure, menu_data, request_path, user):
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

            items.append(item)

        if not items:
            # Empty section! There is no need to add this section.
            continue

        section['items'] = items
        section['url'] = items[0]['url']
        section['classes'] = items[0]['classes']
        menu.append(section)

    return menu


def create_named_menu(menu_structure, menu_data, request_path, user):
    raw = create_menu(menu_structure, menu_data, request_path, user)
    menu = {}
    for name, item in zip(menu_structure, raw):
        menu[name[0]] = dict(
            title=item['title'],
            classes=item['classes'],
            url=item['url'],
        )

    return menu


def create_get_url(namespace):
    def get_url(url_name, *args, **kwargs):
        url_name = fix_url_name(url_name, namespace)

        if ":" not in url_name and namespace:
            # Add namespace
            url_name = f"{namespace}:{url_name}"

        # Creating a lambda function will delay execution. We want to calculate
        # this once we have the structure to avoid unnecessary lookups.
        return lambda: reverse(url_name.strip(':'), args=args, kwargs=kwargs)

    return get_url


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
    elif url_name == 'product_feeds' and namespace:
        url_name = f':{url_name}'

    return url_name


def get_static(path):
    return f"{settings.STATIC_URL}{path}"
