import hmac
import hashlib

from django.core.cache import cache
from django.conf import settings

import arrow


def extra_bundles(request):
    """ Extra bundles link """

    if not request.user.is_authenticated():
        return {'extra_bundle': None}

    extra_cache_key = 'extra_bundle_{}'.format(request.user.id)
    extra_bundle = cache.get(extra_cache_key)

    if extra_bundle is None:
        profile = request.user.profile
        bundles = profile.bundles.all().values_list('register_hash', flat=True)
        if profile.plan.register_hash == '5427f85640fb78728ec7fd863db20e4c':  # JVZoo Pro Plan
            if 'b961a2a0f7101efa5c79b8ac80b75c47' not in bundles:  # JVZoo Elite Bundle
                extra_bundle = {'url': 'http://www.dropified.com/elite', 'title': 'Add Elite Bundle'}
            elif '2fba7df0791f67b61581cfe37e0d7b7d' not in bundles:  # JVZoo Unlimited
                extra_bundle = {'url': 'http://www.dropified.com/unlimited', 'title': 'Add Unlimited Bundle'}
            else:
                extra_bundle = False

            cache.set(extra_cache_key, extra_bundle, timeout=900)

        elif profile.plan.register_hash == 'c0dee42b84c736bb62c61ad0f20b9f53':  # Free Plan for Promote Labs
            extra_bundle = {
                'url': 'http://www.dropified.com/unlimited',
                'title': 'Upgrade To All Drop Shipping Features'
            }

    # Terms of Service update message
    # 2016-08-24 is the date of adding agree to TOS before registering
    tos_update = not request.user.get_config('_tos-update') and \
        arrow.get('2016-08-24').datetime > request.user.date_joined

    return {
        'extra_bundle': extra_bundle,
        'tos_update': tos_update,
    }


def extension_release(request):
    return {
        'DEBUG': settings.DEBUG,
        'extension_release': cache.get('extension_release'),
        'extension_required': cache.get('extension_required')
    }


def intercom(request):
    ctx = {
        'INTERCOM_APP_ID': settings.INTERCOM_APP_ID
    }

    if request.user.is_authenticated() and settings.INTERCOM_SECRET_KEY:
        ctx['INTERCOM_USER_HASH'] = hmac.new(settings.INTERCOM_SECRET_KEY,
                                             str(request.user.id),
                                             hashlib.sha256).hexdigest()

    return ctx


def facebook_pixel(request):
    return {
        'FACEBOOK_PIXEL_ID': settings.FACEBOOK_PIXEL_ID
    }
