import hmac
import hashlib

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.core.urlresolvers import reverse
from django.http import HttpResponseRedirect
from django.http import JsonResponse
from django.utils.crypto import get_random_string
from django.contrib import messages
from django.contrib.auth import login as user_login
from django.contrib.auth import logout as user_logout

import shopify
from requests_oauthlib import OAuth2Session

from raven.contrib.django.raven_compat.models import client as raven_client

from shopified_core import permissions
from leadgalaxy.models import User, ShopifyStore, UserProfile, GroupPlan
from leadgalaxy.utils import attach_webhooks, detach_webhooks, get_plan, create_user_without_signals


AUTHORIZATION_URL = 'https://{}/admin/oauth/authorize'
TOKEN_URL = 'https://{}/admin/oauth/access_token'


def shopify_session(request, state=None):
    return OAuth2Session(
        client_id=settings.SHOPIFY_API_KEY,
        redirect_uri=request.build_absolute_uri(reverse(callback)),
        scope=settings.SHOPIFY_API_SCOPE,
        state=state
    )


def encoded_params_for_signature(params):
    """
    Sort and combine query parameters into a single string,
    excluding those that should be removed and joining with '&'
    """
    def encoded_pairs(params):
        for k, v in params.iteritems():
            if k not in ['signature', 'hmac']:
                # escape delimiters to avoid tampering
                k = str(k).replace("%", "%25").replace("=", "%3D")
                v = str(v).replace("%", "%25")
                yield '{0}={1}'.format(k, v).replace("&", "%26")

    return "&".join(sorted(encoded_pairs(params)))


def verify_hmac_signature(request):
    # message = "code={r[code]}&shop={r[shop]}&state={r[state]}&timestamp={r[timestamp]}".format(r=request.GET)
    message = encoded_params_for_signature(request.GET)
    message_hash = hmac.new(settings.SHOPIFY_API_SECRET.encode(), message.encode(), hashlib.sha256).hexdigest()

    if message_hash != request.GET.get('hmac'):
        raven_client.captureMessage('HMAC Verification failed', level='warning', request=request)
        raise PermissionDenied('HMAC Verification failed')


def shop_username(shop):
    name = shop.lower().strip().encode()
    if len(name) <= 30:
        return name
    else:
        return hmac.new(settings.SHOPIFY_API_SECRET.encode(), name, hashlib.sha256).hexdigest()[:30]


def have_subusers(user):
    return UserProfile.objects.filter(subuser_parent=user).exists()


def subscribe_user_to_default_plan(user):
    from stripe_subscription.models import StripeSubscription
    from stripe_subscription.stripe_api import stripe
    from stripe_subscription.utils import (
        SubscriptionException,
        subscription_end_trial,
        update_subscription,
    )

    # Default plan is Elite Plan
    plan = GroupPlan.objects.get(slug='elite')

    user.profile.create_stripe_customer()

    sub = stripe.Subscription.create(
        customer=user.stripe_customer.customer_id,
        plan=plan.stripe_plan.stripe_id,
        metadata={'plan_id': plan.id, 'user_id': user.id}
    )

    update_subscription(user, plan, sub)

    if not user.stripe_customer.can_trial:
        try:
            subscription_end_trial(user, raven_client, delete_on_error=True)

        except SubscriptionException:
            raven_client.captureException()
            StripeSubscription.objects.filter(subscription_id=sub.id).delete()
            raise

        except:
            raven_client.captureException()
            raise

    profile = user.profile
    profile.plan = plan
    profile.save()


def index(request):
    verify_hmac_signature(request)

    try:
        store = ShopifyStore.objects.get(shop=request.GET['shop'], is_active=True)
    except ShopifyStore.DoesNotExist:
        return HttpResponseRedirect(reverse(install, kwargs={'store': request.GET['shop'].split('.')[0]}))
    except ShopifyStore.MultipleObjectsReturned:
        # TODO: Handle multi stores
        if request.user.is_authenticated():
            return HttpResponseRedirect('/')
        else:
            return HttpResponseRedirect('/accounts/login/')

    except:
        raven_client.captureException()
        return HttpResponseRedirect('/accounts/login/')

    if request.user.is_authenticated():
        if permissions.user_can_view(request.user, store, raise_on_error=False, superuser_can=False):
            messages.success(request, u'Welcome Back, {}'.format(request.user.first_name))
            return HttpResponseRedirect('/')
        else:
            user_logout(request)

    user = store.user
    if not have_subusers(user):
        user.backend = settings.AUTHENTICATION_BACKENDS[0]
        user_login(request, user)
    else:
        request.session['sudo_user'] = user.id
        return HttpResponseRedirect(reverse('sudo_login'))

    return HttpResponseRedirect('/')


def install(request, store):
    if not store.endswith('myshopify.com'):
        store = '{}.myshopify.com'.format(store)

    reinstall_store = request.GET.get('reinstall') and \
        permissions.user_can_view(request.user, ShopifyStore.objects.get(id=request.GET.get('reinstall')), superuser_can=False)

    if request.user.is_authenticated():
        user = request.user

        if user.is_subuser:
            messages.error(request, 'Sub-Users can not add new stores.')
            return HttpResponseRedirect('/')

        can_add, total_allowed, user_count = permissions.can_add_store(user)

        if not can_add and not reinstall_store:
            if user.profile.plan.is_free and user.can_trial():
                subscribe_user_to_default_plan(user)

            else:
                raven_client.captureMessage(
                    'Add Extra Store',
                    level='warning',
                    extra={
                        'user': user.email,
                        'store': store,
                        'plan': user.profile.plan.title,
                        'stores': user.profile.get_shopify_stores().count()
                    }
                )

                plans_url = request.build_absolute_uri('/user/profile#plan')
                if user.profile.plan.is_free and not user_count:
                    messages.error(
                        request,
                        'Please Activate your account first by visiting '
                        '<a href="{}">Profile page</a>'.format(plans_url))
                else:
                    messages.error(
                        request,
                        'Your plan does not support connecting another Shopify store. '
                        'Please <a href={}>Upgrade your current plan</a> or <a href="mailto:support@dropified.com">'
                        'contact support</a> to learn how to connect more stores'.format(plans_url))

                return HttpResponseRedirect('/')

    state = get_random_string(16)
    request.session['shopify_state'] = state

    if reinstall_store:
        request.session['shopify_reinstall'] = request.GET.get('reinstall')

    shopify = shopify_session(request, state=state)
    authorization_url, state = shopify.authorization_url(AUTHORIZATION_URL.format(store))

    return HttpResponseRedirect(authorization_url)


def callback(request):
    verify_hmac_signature(request)
    if request.session.get('shopify_state', True) != request.GET.get('state', False):
        raven_client.captureMessage(
            'State does not match',
            level='warning', request=request,
            extra={'Current': request.GET.get('state'),
                   'ShouldBe': request.session.get('shopify_state')})

        # raise PermissionDenied('State not matching')

    shop = request.GET['shop'].strip()

    oauth_session = shopify_session(request)

    token = oauth_session.fetch_token(
        token_url=TOKEN_URL.format(shop),
        client_secret=settings.SHOPIFY_API_SECRET,
        code=request.GET['code'])

    user = request.user
    store = None

    if request.session.get('shopify_reinstall'):
        store = ShopifyStore.objects.get(id=request.session['shopify_reinstall'])

        del request.session['shopify_reinstall']

        if not permissions.user_can_view(request.user, store, raise_on_error=False, superuser_can=False):
            messages.success(request, u'You don\'t have access to this store')
            return HttpResponseRedirect('/')

        try:
            detach_webhooks(store)
        except:
            raven_client.captureException(level='warning')

        store.update_token(token)

        try:
            attach_webhooks(store)
        except:
            raven_client.captureException(level='warning')

        messages.success(request, u'Your store <b>{}</b> has been re-installed!'.format(store.title))

        return HttpResponseRedirect('/')
    else:
        try:
            store = ShopifyStore.objects.get(shop=request.GET['shop'], is_active=True)

            # We have one store/user account, try to log him in if he doesn't have sub users
            if user.is_authenticated():
                if permissions.user_can_view(request.user, store, raise_on_error=False, superuser_can=False):
                    store.update_token(token)
                    messages.success(request, u'Welcome Back, {}'.format(user.first_name))
                    return HttpResponseRedirect('/')
            else:
                # handle the Shopify redirect flow
                return index(request)

        except ShopifyStore.DoesNotExist:
            pass
        except ShopifyStore.MultipleObjectsReturned:
            # TODO: Handle multi stores
            raven_client.captureException()
        except:
            raven_client.captureException()

    if user.is_authenticated():
        from_shopify_store = (user.get_config('shopify_app_store') or
                              user.profile.shopify_app_store or
                              user.profile.plan.payment_gateway == 'shopify')
    else:
        from_shopify_store = True

    if from_shopify_store and user.is_authenticated():
        user_logout(request)

    if from_shopify_store:
        # New User coming from Shopify Apps Store

        # check if we have a user with this shop as the username
        if User.objects.filter(username__iexact=shop_username(shop), profile__shopify_app_store=True).exists():
            user = User.objects.get(username__iexact=shop_username(shop), profile__shopify_app_store=True)
        else:
            # TODO: Check if email already exists and ask the user what to do
            shopify.ShopifyResource.activate_session(shopify.Session(shop, token['access_token']))

            shop_info = shopify.Shop.current()
            username = shop_username(shop)

            user, profile = create_user_without_signals(
                username=username,
                email=shop_info.email,
                password=get_random_string(20))

            user.set_config('shopify_app_store', True)

            profile.shopify_app_store = True
            profile.change_plan(get_plan(
                payment_gateway='shopify',
                plan_slug='shopify-free-plan'))

            profile.save()

        user.backend = settings.AUTHENTICATION_BACKENDS[0]
        user_login(request, user)

    try:
        store = ShopifyStore.objects.get(user=user, shop=shop, is_active=True)
        store.update_token(token, shop=shop)

    except ShopifyStore.DoesNotExist:
        can_add, total_allowed, user_count = permissions.can_add_store(user)

        if not from_shopify_store and not can_add:
            plans_url = request.build_absolute_uri('/user/profile#plan')

            if user.profile.plan.is_free:
                raven_client.captureMessage(
                    'Activate your account first',
                    level='warning',
                    extra={'user': user.email, 'store': store, 'pos': 2}
                )

                messages.error(
                    request,
                    'Please Activate your account first by visiting: '
                    '<a href="{}">Your Profile page</a>'.format(plans_url))
            else:
                messages.error(
                    request,
                    'Your plan does not support connecting another Shopify store. '
                    'Please <a href={}>Upgrade your current plan</a> or <a href="mailto:support@dropified.com">'
                    'contact support</a> to learn how to connect more stores'.format(plans_url))

            return HttpResponseRedirect('/')

        store = ShopifyStore.objects.filter(user=user, shop=shop, version=2, is_active=False) \
                                    .order_by('uninstalled_at', '-id').first()
        if store:
            store.is_active = True
            store.uninstalled_at = None
        else:
            store = ShopifyStore(user=user, shop=shop)

        store.update_token(token, shop=shop)

        if not permissions.user_can_add(user, store, raise_on_error=False):
            messages.success(request, u'You don\'t authorization to add this store')
            return HttpResponseRedirect('/')

        try:
            shopify.ShopifyResource.activate_session(shopify.Session(shop, token['access_token']))

            shop_info = shopify.Shop.current()
            store.title = shop_info.name
            store.currency_format = shop_info.money_in_emails_format
            store.refresh_info(info=shop_info.to_dict(), commit=False)

            if shop_info.shop_owner and not user.first_name and not user.last_name:
                fullname = shop_info.shop_owner.split(' ')
                user.first_name, user.last_name = fullname[0], ' '.join(fullname[1:])
                user.save()

        except:
            raven_client.captureException()
            return JsonResponse({'error': 'An error occurred when installing Dropified on your store.'}, status=500)

        store.save()

        attach_webhooks(store)

        if from_shopify_store:
            messages.success(request, u'Please select a plan to start your free trial!'.format(store.title))
            return HttpResponseRedirect('/user/profile#plan')
        else:
            messages.success(request, u'Your store <b>{}</b> has been added!'.format(store.title))

    return HttpResponseRedirect('/')
