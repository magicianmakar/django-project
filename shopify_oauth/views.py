import hmac
import hashlib

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from django.urls import reverse
from django.http import HttpResponseRedirect
from django.http import JsonResponse
from django.utils.crypto import get_random_string
from django.contrib import messages
from django.contrib.auth import login as user_login
from django.contrib.auth import logout as user_logout

import shopify
from django.views.generic import TemplateView
from requests_oauthlib import OAuth2Session

from lib.exceptions import capture_exception, capture_message

from shopified_core import permissions
from leadgalaxy.models import SHOPIFY_API_VERSION, User, ShopifyStore, UserProfile, GroupPlan
from leadgalaxy.utils import attach_webhooks, detach_webhooks, get_plan, create_user_without_signals
from shopified_core.utils import app_link, jwt_decode, jwt_encode


AUTHORIZATION_URL = 'https://{}/admin/oauth/authorize'
TOKEN_URL = 'https://{}/admin/oauth/access_token'


def is_private_label_app(request):
    return request.session.get('shopify_api') == 'private-label'


def get_shopify_key(request):
    if is_private_label_app(request):
        return settings.SHOPIFY_PRIVATE_LABEL_KEY
    else:
        return settings.SHOPIFY_API_KEY


def get_shopify_secret(request):
    if is_private_label_app(request):
        return settings.SHOPIFY_PRIVATE_LABEL_SECRET
    else:
        return settings.SHOPIFY_API_SECRET


def get_shopify_scope(request):
    scopes = settings.SHOPIFY_API_SCOPE
    if is_private_label_app(request):
        if 'read_all_orders' in scopes:
            scopes = scopes.split(',')
            scopes.remove('read_all_orders')
            return ','.join(scopes)

    return scopes


def shopify_session(request, state=None, client_id=None):
    if client_id is None:
        client_id = get_shopify_key(request)

    return OAuth2Session(
        client_id=client_id,
        redirect_uri=request.build_absolute_uri(reverse(callback)),
        scope=get_shopify_scope(request),
        state=state
    )


def encoded_params_for_signature(params):
    """
    Sort and combine query parameters into a single string,
    excluding those that should be removed and joining with '&'
    """
    def encoded_pairs(params):
        for k, v in params.items():
            if k not in ['signature', 'hmac']:
                # escape delimiters to avoid tampering
                k = str(k).replace("%", "%25").replace("=", "%3D")
                v = str(v).replace("%", "%25")
                yield '{0}={1}'.format(k, v).replace("&", "%26")

    return "&".join(sorted(encoded_pairs(params)))


def verify_hmac_signature(request, secret=None):
    if secret is None:
        secret = get_shopify_secret(request)

    message = encoded_params_for_signature(request.GET)
    message_hash = hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()

    if message_hash != request.GET.get('hmac'):
        capture_message('HMAC Verification failed', level='warning', request=request)

        if not settings.DEBUG:
            raise PermissionDenied('HMAC Verification failed')


def shop_username(shop):
    name = shop.lower().strip()
    if len(name) <= 30:
        return name
    else:
        encoded_name = hmac.new(settings.SHOPIFY_API_SECRET.encode(), name.encode(), hashlib.sha256).hexdigest()
        return encoded_name[:30]


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

    # Default paid plan is Builder Plan
    plan = GroupPlan.objects.get(slug='builder')

    user.profile.create_stripe_customer()

    sub = stripe.Subscription.create(
        customer=user.stripe_customer.customer_id,
        plan=plan.stripe_plan.stripe_id,
        metadata={'plan_id': plan.id, 'user_id': user.id}
    )

    update_subscription(user, plan, sub)

    if not user.stripe_customer.can_trial:
        try:
            subscription_end_trial(user, delete_on_error=True)

        except SubscriptionException:
            capture_exception()
            StripeSubscription.objects.filter(subscription_id=sub.id).delete()
            raise

        except:
            capture_exception()
            raise

    profile = user.profile
    profile.plan = plan
    profile.save()


def index(request):
    request.session['shopify_api'] = 'main'

    verify_hmac_signature(request)

    try:
        store = ShopifyStore.objects.exclude(private_label=True).get(shop=request.GET['shop'], is_active=True)

    except ShopifyStore.DoesNotExist:
        if request.user.is_authenticated:
            user_logout(request)

        return HttpResponseRedirect(reverse(install, kwargs={'store': request.GET['shop'].split('.')[0]}))

    except ShopifyStore.MultipleObjectsReturned:
        # TODO: Handle multi stores
        if request.user.is_authenticated:
            return HttpResponseRedirect('/')
        else:
            token = jwt_encode({'shop': request.GET['shop']})

            return HttpResponseRedirect(app_link(reverse('shopify_account_select'), token=token))

    except:
        capture_exception()
        return HttpResponseRedirect(redirect('login'))

    if request.user.is_authenticated:
        if permissions.user_can_view(request.user, store, raise_on_error=False, superuser_can=False):
            messages.success(request, 'Welcome Back, {}'.format(request.user.first_name))
            return HttpResponseRedirect('/')
        else:
            user_logout(request)

    user = store.user
    from_shopify_store = user.profile.from_shopify_app_store()

    if not have_subusers(user) or from_shopify_store:
        user.backend = settings.AUTHENTICATION_BACKENDS[0]
        user_login(request, user)
    else:
        request.session['sudo_user'] = user.id
        return HttpResponseRedirect(reverse('sudo_login'))

    return HttpResponseRedirect('/')


def private_label_index(request):
    request.session['shopify_api'] = 'private-label'

    verify_hmac_signature(request, secret=settings.SHOPIFY_PRIVATE_LABEL_SECRET)

    try:
        store = ShopifyStore.objects.get(shop=request.GET['shop'], is_active=True, private_label=True)

    except ShopifyStore.DoesNotExist:
        if request.user.is_authenticated:
            user_logout(request)

        return HttpResponseRedirect(reverse(install, kwargs={'store': request.GET['shop'].split('.')[0]}))

    except ShopifyStore.MultipleObjectsReturned:
        # TODO: Handle multi stores
        if request.user.is_authenticated:
            return HttpResponseRedirect('/')
        else:
            return HttpResponseRedirect(redirect('login'))

    except:
        capture_exception()
        return HttpResponseRedirect(redirect('login'))

    if request.user.is_authenticated:
        if permissions.user_can_view(request.user, store, raise_on_error=False, superuser_can=False):
            messages.success(request, 'Welcome Back, {}'.format(request.user.first_name))
            return HttpResponseRedirect('/')
        else:
            user_logout(request)

    user = store.user
    from_shopify_store = user.profile.from_shopify_app_store()

    if not have_subusers(user) or from_shopify_store:
        user.backend = settings.AUTHENTICATION_BACKENDS[0]
        user_login(request, user)
    else:
        request.session['sudo_user'] = user.id
        return HttpResponseRedirect(reverse('sudo_login'))

    return HttpResponseRedirect('/')


def install(request, store):
    if not store.endswith('myshopify.com'):
        store = f'{store}.myshopify.com'

    reinstall_store = request.GET.get('reinstall') and \
        permissions.user_can_view(request.user, ShopifyStore.objects.get(id=request.GET.get('reinstall')), superuser_can=False)

    if request.user.is_authenticated:
        user = request.user

        if user.is_subuser:
            messages.error(request, 'Sub-Users can not add new stores.')
            return HttpResponseRedirect('/')

        can_add, total_allowed, user_count = permissions.can_add_store(user)

        if not can_add and not reinstall_store:
            if user.profile.plan.is_free and user.can_trial() and not user.profile.from_shopify_app_store():
                subscribe_user_to_default_plan(user)
            else:
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
        capture_message(
            'State does not match',
            level='warning', request=request,
            extra={'Current': request.GET.get('state'),
                   'ShouldBe': request.session.get('shopify_state')})

        # raise PermissionDenied('State not matching')

    shop = request.GET['shop'].strip()

    oauth_session = shopify_session(request)

    token = oauth_session.fetch_token(
        token_url=TOKEN_URL.format(shop),
        client_secret=get_shopify_secret(request),
        code=request.GET['code'])

    user = request.user
    store = None

    if request.session.get('shopify_reinstall'):
        store = ShopifyStore.objects.get(id=request.session['shopify_reinstall'])

        del request.session['shopify_reinstall']

        if not permissions.user_can_view(request.user, store, raise_on_error=False, superuser_can=False):
            messages.success(request, 'You don\'t have access to this store')
            return HttpResponseRedirect('/')

        try:
            detach_webhooks(store)
        except:
            capture_exception(level='warning')

        store.update_token(token)

        try:
            attach_webhooks(store)
        except:
            capture_exception(level='warning')

        messages.success(request, 'Your store <b>{}</b> has been re-installed!'.format(store.title))

        return HttpResponseRedirect('/')
    else:
        try:
            if is_private_label_app(request):
                store = ShopifyStore.objects.get(shop=request.GET['shop'], is_active=True, private_label=True)
            else:
                store = ShopifyStore.objects.exclude(private_label=True).get(shop=request.GET['shop'], is_active=True)

            # We have one store/user account, try to log him in if he doesn't have sub users
            if user.is_authenticated:
                if permissions.user_can_view(request.user, store, raise_on_error=False, superuser_can=False):
                    store.update_token(token)
                    messages.success(request, 'Welcome Back, {}'.format(user.first_name))
                    return HttpResponseRedirect('/')
            else:
                # handle the Shopify redirect flow
                return index(request)

        except ShopifyStore.DoesNotExist:
            pass
        except ShopifyStore.MultipleObjectsReturned:
            # TODO: Handle multi stores
            capture_exception()
        except:
            capture_exception()

    if user.is_authenticated:
        from_shopify_store = user.profile.from_shopify_app_store()
    else:
        from_shopify_store = True

    if from_shopify_store and user.is_authenticated:
        user_logout(request)

    if from_shopify_store:
        # New User coming from Shopify Apps Store

        # check if we have a user with this shop as the username
        if User.objects.filter(username__iexact=shop_username(shop), profile__shopify_app_store=True).exists():
            user = User.objects.get(username__iexact=shop_username(shop), profile__shopify_app_store=True)
        else:
            # TODO: Check if email already exists and ask the user what to do
            session = shopify.Session(
                shop_url=shop,
                version=SHOPIFY_API_VERSION,
                token=token['access_token'])

            shopify.ShopifyResource.activate_session(session)

            shop_info = shopify.Shop.current()
            username = shop_username(shop)

            user, profile = create_user_without_signals(
                username=username,
                email=shop_info.email,
                password=get_random_string(20))
            user.set_config('__phone', shop_info.phone)
            user.set_config('shopify_app_store', True)
            profile.shopify_app_store = True

            if is_private_label_app(request):
                profile.private_label = True
                profile.change_plan(get_plan(
                    payment_gateway='shopify',
                    plan_slug='shopify-plod-free-plan'))
            else:
                profile.change_plan(get_plan(
                    payment_gateway='shopify',
                    plan_slug='shopify-free-plan'))

            profile.save()

        user.backend = settings.AUTHENTICATION_BACKENDS[0]
        user_login(request, user)

    try:
        if is_private_label_app(request):
            store = ShopifyStore.objects.get(user=user, shop=shop, is_active=True, private_label=True)
        else:
            store = ShopifyStore.objects.exclude(private_label=True).get(user=user, shop=shop, is_active=True)

        store.update_token(token, shop=shop)

    except ShopifyStore.DoesNotExist:
        can_add, total_allowed, user_count = permissions.can_add_store(user)

        if not from_shopify_store and not can_add:
            plans_url = request.build_absolute_uri('/user/profile#plan')

            if user.profile.plan.is_free:
                capture_message(
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

        store = ShopifyStore.objects.filter(user=user, shop=shop, version=2, is_active=False)

        if is_private_label_app(request):
            store = store.filter(private_label=True)
        else:
            store = store.exclude(private_label=True)

        store = store.order_by('uninstalled_at', '-id').first()

        if store:
            store.is_active = True
            store.uninstalled_at = None
        else:
            store = ShopifyStore(user=user, shop=shop)

        if is_private_label_app(request):
            store.private_label = True

        store.update_token(token, shop=shop)

        if not permissions.user_can_add(user, store, raise_on_error=False):
            messages.success(request, 'You don\'t authorization to add this store')
            return HttpResponseRedirect('/')

        try:
            session = shopify.Session(
                shop_url=shop,
                version=SHOPIFY_API_VERSION,
                token=token['access_token'])

            shopify.ShopifyResource.activate_session(session)

            shop_info = shopify.Shop.current()
            store.title = shop_info.name
            store.currency_format = shop_info.money_in_emails_format
            store.refresh_info(info=shop_info.to_dict(), commit=False)

            if shop_info.shop_owner and not user.first_name and not user.last_name:
                fullname = shop_info.shop_owner.split(' ')
                user.first_name, user.last_name = fullname[0], ' '.join(fullname[1:])
                user.save()

        except:
            capture_exception()
            return JsonResponse({'error': 'An error occurred when installing Dropified on your store.'}, status=500)

        store.save()

        try:
            attach_webhooks(store)
        except:
            capture_exception(level='warning')

        if from_shopify_store:
            messages.success(request, 'Please select a plan to activate your free trial!')
            return HttpResponseRedirect('/user/profile#plan')
        else:
            messages.success(request, 'Your store <b>{}</b> has been added!'.format(store.title))

    return HttpResponseRedirect('/')


class AccountSelectView(TemplateView):
    template_name = 'shopify/select.html'

    def get_context_data(self, **kwargs: dict) -> dict:
        ctx = super().get_context_data(**kwargs)

        token = self.request.GET.get('token')
        if token:
            data = jwt_decode(token)
            stores = ShopifyStore.objects.exclude(private_label=True).filter(shop=data['shop'], is_active=True)

            ctx['stores'] = []
            for store in stores:
                ctx['stores'].append({
                    'store': store,
                    'url_token': jwt_encode({'store': store.id}, expire=0.16)
                })

        return ctx

    def get(self, request, *args, **kwargs):
        login = self.request.GET.get('login')
        if login:
            data = jwt_decode(login)
            store = ShopifyStore.objects.get(id=data['store'])
            user = store.user

            if not have_subusers(user) or user.profile.from_shopify_app_store():
                user.backend = settings.AUTHENTICATION_BACKENDS[0]
                user_login(request, user)
                return HttpResponseRedirect('/')
            else:
                request.session['sudo_user'] = user.id
                return HttpResponseRedirect(reverse('sudo_login'))

        else:
            return super().get(request, *args, **kwargs)
