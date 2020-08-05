import hmac
import hashlib

from django.core.cache import cache
from django.conf import settings

import arrow
import datetime

from shopified_core.permissions import can_add_store
from leadgalaxy.side_menu import (
    get_menu_structure,
    get_menu_item_data,
    create_menu,
    get_namespace,
    create_named_menu,
)
from stripe_subscription.stripe_api import stripe


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

    dropified_challenge = request.user.get_config('__dropified-challenge')
    new_menu_active = request.user.get_config('_new-menu-active')

    return {
        'tos_update': tos_update,
        'tos_accept': tos_accept,
        'dropified_challenge': dropified_challenge,
        'new_menu_active': new_menu_active,
    }


def store_limits_check(request):
    stores_limit_reached = False
    stores_limit_max = 1

    if request.user.is_authenticated and \
            not request.user.profile.is_subuser and \
            not request.user.profile.plan.is_paused and \
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
                stores_limit_max = total_allowed
            else:
                # Only cache value if the store limit is not reached
                cache.set(cache_key, False, timeout=900)

        if request.user.models_user.profile.plan.is_paused:
            stores_limit_reached = False

    return {
        'stores_limit_reached': stores_limit_reached,
        'stores_limit_max': stores_limit_max,
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
        ctx['INTERCOM_USER_HASH'] = hmac.new(settings.INTERCOM_SECRET_KEY.encode(),
                                             str(request.user.id).encode(),
                                             hashlib.sha256).hexdigest()

    return ctx


def facebook_pixel(request):
    return {
        'FACEBOOK_PIXEL_ID': settings.FACEBOOK_PIXEL_ID
    }


def tapafilate_conversaion(request):
    tapafilate_conversaion = None

    # if called from CF order confirmation (not logged in, called via iframe/js with special GET parameter)
    tapfiliate_user_email = request.GET.get('tapfiliate_user_email', False)
    if tapfiliate_user_email:
        # getting stripe customer via API (because of posible webhook delay), most recent first
        stripe_cus = stripe.Customer.list(email=tapfiliate_user_email, limit=1)
        if len(stripe_cus.data):
            # check if time difference is less than 7 days (same as cache)
            stripe_cus_created = datetime.datetime.fromtimestamp(float(stripe_cus.data[0].created))
            seconds_passed = (datetime.datetime.now() - stripe_cus_created).total_seconds()
            if seconds_passed < 99999604800:
                tapafilate_conversaion = {"affiliate": stripe_cus.data[0].id,
                                          "email": stripe_cus.data[0].email,
                                          "full_name": stripe_cus.data[0].metadata.name}

    # fallback to "logined" method
    elif request.user.is_authenticated \
            and request.user.is_stripe_customer() \
            and cache.get('affilaite_{}'.format(request.user.stripe_customer.customer_id)):
        tapafilate_conversaion = {"affiliate": request.user.stripe_customer.customer_id,
                                  "email": request.user.email,
                                  "full_name": request.user.get_full_name}

    return {
        'tapafilate_conversaion': tapafilate_conversaion
    }


def add_side_menu(request):
    try:
        namespace = get_namespace(request)
    except:
        namespace = ''

    menu_data = get_menu_item_data()
    menu_structure = get_menu_structure(namespace)

    header = create_menu(menu_structure['header'], menu_data, request, namespace)
    body = create_menu(menu_structure['body'], menu_data, request, namespace)
    footer = create_menu(menu_structure['footer'], menu_data, request, namespace)
    named = create_named_menu(menu_structure['named'], menu_data, request, namespace)

    return {'sidemenu': {'header': header,
                         'body': body,
                         'footer': footer,
                         'named': named}}
