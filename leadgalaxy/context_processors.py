import hmac
import hashlib

from django.core.cache import cache
from django.conf import settings
from django.contrib import messages

import arrow
import datetime

from shopified_core.permissions import can_add_store, can_add_subuser
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
    additional_stores = False
    cost_per_store = None

    if request.user.is_authenticated and \
            not request.user.profile.is_subuser and \
            not request.user.profile.plan.is_paused and \
            not request.path.startswith('/user/profile') and \
            not settings.DEBUG:

        user_plan = request.user.profile.plan
        additional_stores = user_plan.extra_stores
        cost_per_store = user_plan.extra_store_cost
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
        'additional_stores': additional_stores,
        'cost_per_store': cost_per_store,
    }


def subuser_limits_check(request):
    subusers_limit_reached = False
    subusers_limit_max = 1
    additional_subusers = False
    cost_per_subuser = None

    if request.user.is_authenticated and \
            not request.user.profile.plan.is_paused and \
            not request.path.startswith('/user/profile') and \
            not settings.DEBUG:

        user_plan = request.user.profile.plan
        additional_subusers = user_plan.extra_subusers
        cost_per_subuser = user_plan.extra_subuser_cost
        cache_key = 'subuser_limit_reached_{}'.format(request.user.id)
        cached_value = cache.get(cache_key)

        if cached_value is not None:
            subusers_limit_reached = cached_value
        else:
            can_add, total_allowed, user_count = can_add_subuser(request.user)
            total_allowed += request.user.extra_sub_user.count()
            if not can_add and total_allowed < user_count:  # if the user `can_add` a subuser he definetly didn't reach the limit
                subusers_limit_reached = True
                subusers_limit_max = total_allowed
            else:
                # Only cache value if the subuser limit is not reached
                cache.set(cache_key, False, timeout=900)

        if request.user.models_user.profile.plan.is_paused:
            subusers_limit_reached = False

    return {
        'subusers_limit_reached': subusers_limit_reached,
        'subusers_limit_max': subusers_limit_max,
        'additional_subusers': additional_subusers,
        'cost_per_subuser': cost_per_subuser,
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

    menu_data = get_menu_item_data(request)
    menu_structure = get_menu_structure(namespace)

    header = create_menu(menu_structure['header'], menu_data, request, namespace)
    body = create_menu(menu_structure['body'], menu_data, request, namespace)
    footer = create_menu(menu_structure['footer'], menu_data, request, namespace)
    named = create_named_menu(menu_structure['named'], menu_data, request, namespace)

    return {'sidemenu': {'header': header,
                         'body': body,
                         'footer': footer,
                         'named': named}}


def check_shopify_pending_subscription(request):
    """
    https://help.shopify.com/en/manual/your-account/manage-billing/your-invoice/apps#app-usage-charges
    Apps that issue usage charges include a capped amount that prevents billing from exceeding a maximum
    threshold over the duration of the billing period. To *continue using an app* after exceeding a capped
    amount, you need to agree to a new usage charge. This prevents you from being charged for any usage
    over and above the capped amount.
    """
    if not request.user.is_authenticated:
        return {}

    if not request.user.profile.from_shopify_app_store():
        return {}

    shopify_subscription = request.user.profile.get_current_shopify_subscription()
    if shopify_subscription is None:
        return {}

    if not shopify_subscription.update_capped_amount_url:
        return {}

    message = 'Please, confirm your pending subscription update '
    message += f'<a href="{shopify_subscription.update_capped_amount_url}">here</a>. '

    add_message = None
    if shopify_subscription.updated_at > arrow.get().shift(hours=-24):
        message += 'It will expire within 24 hours. '
        add_message = messages.error

    elif shopify_subscription.updated_at > arrow.get().shift(hours=-48):
        message += 'It will expire within 48 hours. '
        add_message = messages.warning

    if add_message is not None:
        message += 'Shopify automatically cancels expired subscriptions after 30 days.'
        add_message(request, message)
    return {}
