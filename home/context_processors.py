import re
from operator import attrgetter


def all_stores(request, do_sync=True):
    user = request.user
    if not user.is_authenticated:
        return {}

    platforms = ['shopify', 'woo', 'chq', 'bigcommerce', 'gear', 'gkart', 'ebay', 'fb', 'google']
    include_non_onboarded = bool(re.match(f"/({'|'.join(platforms)})?/?$", request.path))
    stores = {
        'shopify': list(user.profile.get_shopify_stores()),
        'chq': list(user.profile.get_chq_stores()),
        'woo': list(user.profile.get_woo_stores()),
        'ebay': list(user.profile.get_ebay_stores(do_sync=do_sync)),
        'fb': list(user.profile.get_fb_stores(do_sync=do_sync, include_non_onboarded=include_non_onboarded,
                                              use_cached=True)),
        'google': list(user.profile.get_google_stores(do_sync=do_sync, use_cached=True)),
        'gear': list(user.profile.get_gear_stores()),
        'gkart': list(user.profile.get_gkart_stores()),
        'bigcommerce': list(user.profile.get_bigcommerce_stores()),
        'fb_marketplace': list(user.profile.get_fb_marketplace_stores()),
        'all': [],
        'grouped': {},
        'type_count': 0,
    }

    for key, val in stores.items():
        if key not in ['all', 'type_count'] and len(val):
            stores['all'].extend(val)
            stores['type_count'] += 1

    sort_key = 'list_index' if any([v.list_index for v in stores['all']]) else 'created_at'
    stores['all'] = sorted(stores['all'], key=attrgetter(sort_key))
    stores['first'] = stores['all'][0] if stores['type_count'] > 0 else None

    for platform in platforms:
        if len(stores[platform]):
            stores['grouped'][platform] = stores[platform]

    return {
        'user_stores': stores
    }
