from django.core.cache import cache


def extra_bundles(request):
    """ Extra bundles link """

    extra_cache_key = 'extra_bundle_{}'.format(request.user.id)
    extra_cache = cache.get(extra_cache_key)

    if extra_cache is not None:
        extra_bundle = extra_cache
    else:
        profile = request.user.profile
        bundles = profile.bundles.all().values_list('register_hash', flat=True)
        if profile.plan.register_hash == '5427f85640fb78728ec7fd863db20e4c':  # JVZoo Pro Plan
            if 'b961a2a0f7101efa5c79b8ac80b75c47' not in bundles:  # JVZoo Elite Bundle
                extra_bundle = {'url': 'http://www.shopifiedapp.com/elite', 'title': 'Add Elite Bundle'}
            elif '2fba7df0791f67b61581cfe37e0d7b7d' not in bundles:  # JVZoo Unlimited
                extra_bundle = {'url': 'http://www.shopifiedapp.com/unlimited', 'title': 'Add Unlimited Bundle'}
            else:
                extra_bundle = False

            cache.set(extra_cache_key, extra_bundle, timeout=900)

    return {
        'extra_bundle': extra_bundle
    }
