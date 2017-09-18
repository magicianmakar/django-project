import hmac
import hashlib

from django.core.cache import cache
from django.conf import settings

import arrow


def extra_bundles(request):
    """ Extra bundles link """
    if not request.user.is_authenticated():
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
