import hmac
import hashlib

from django.core.cache import cache
from django.conf import settings

import arrow

from shopified_core.permissions import can_add_store
from shopified_core.utils import execute_once_in


def extra_bundles(request):
    """ Extra bundles link """
    if not request.user.is_authenticated:
        return {}

    # Terms of Service update message
    # 2016-08-24 is the date of adding agree to TOS before registering
    tos_update = not request.user.get_config('_tos-update') and \
        arrow.get('2016-08-24').datetime > request.user.date_joined

    tos_accept = not request.user.get_config('_tos-accept') and \
        not request.user.is_subuser and \
        not request.path.startswith('/pages/') and \
        arrow.get('2017-08-27').datetime < request.user.date_joined

    return {
        'tos_update': tos_update,
        'tos_accept': tos_accept,
    }


def store_limits_check(request):
    stores_limit_reached = False

    if request.user.is_authenticated and \
            not request.user.profile.is_subuser and \
            not request.path.startswith('/user/profile') and \
            not settings.DEBUG:

        cache_key = 'stores_limit_reached_{}'.format(request.user.id)
        cached_value = cache.get(cache_key)

        if cached_value is not None:
            stores_limit_reached = cached_value
        else:
            can_add, total_allowed, user_count = can_add_store(request.user)
            if not can_add and total_allowed < user_count:  # if the user `can_add` a store he definetly didn't reach the limit
                stores_limit_reached = True

                @execute_once_in([request.user.id], 120)
                def record_limit_event(can_add, total_allowed, user_count):
                    from raven.contrib.django.raven_compat.models import client
                    client.captureMessage('Store Limit Reached', extra={
                        'can_add': can_add,
                        'total_allowed': total_allowed,
                        'user_count': user_count
                    })

                record_limit_event(can_add, total_allowed, user_count)

            else:
                # Only cache value if the store limit is not reached
                cache.set(cache_key, False, timeout=900)

    return {
        'stores_limit_reached': stores_limit_reached
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

    if request.user.is_authenticated and settings.INTERCOM_SECRET_KEY:
        ctx['INTERCOM_USER_HASH'] = hmac.new(settings.INTERCOM_SECRET_KEY,
                                             str(request.user.id),
                                             hashlib.sha256).hexdigest()

    return ctx


def facebook_pixel(request):
    return {
        'FACEBOOK_PIXEL_ID': settings.FACEBOOK_PIXEL_ID
    }


def tapafilate_conversaion(request):
    affilaite = None

    if request.user.is_authenticated \
            and request.user.is_stripe_customer() \
            and cache.get('affilaite_{}'.format(request.user.stripe_customer.customer_id)):
            affilaite = request.user.stripe_customer.customer_id

    return {
        'tapafilate_conversaion': affilaite
    }
