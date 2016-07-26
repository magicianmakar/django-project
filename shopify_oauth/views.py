from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.urlresolvers import reverse
from django.http import HttpResponseRedirect
from django.http import JsonResponse
from django.utils.crypto import get_random_string
from django.contrib import messages
from django.contrib.auth import login as user_login

from requests_oauthlib import OAuth2Session

from raven.contrib.django.raven_compat.models import client as raven_client

from leadgalaxy.models import ShopifyStore
from leadgalaxy.utils import attach_webhooks

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


def verify_shopify_webhook(request):
    import hmac
    from hashlib import sha256

    # message = "code={r[code]}&shop={r[shop]}&state={r[state]}&timestamp={r[timestamp]}".format(r=request.GET)
    message = encoded_params_for_signature(request.GET)
    message_hash = hmac.new(settings.SHOPIFY_API_SECRET.encode(), message.encode(), sha256).hexdigest()

    if message_hash != request.GET.get('hmac'):
        raise PermissionDenied('HMAC Verification failed')


def index(request):
    verify_shopify_webhook(request)

    try:
        store = ShopifyStore.objects.get(shop=request.GET['shop'], is_active=True)
    except ShopifyStore.DoesNotExist:
        return HttpResponseRedirect(reverse(install, kwargs={'store': request.GET['shop'].split('.')[0]}))
    except ShopifyStore.MultipleObjectsReturned:
        if request.user.is_authenticated():
            if not request.user.profile.get_active_stores(flat=True).filter(shop=request.GET['shop']).exists():
                messages.error(request, 'You don\'t have access to the <b>{}</b> store'.format(request.GET['shop']))

            return HttpResponseRedirect('/')
        else:
            return HttpResponseRedirect('/accounts/login/')

    except:
        raven_client.captureException()
        return HttpResponseRedirect('/accounts/login/')

    if request.user.is_authenticated():
        if store.id not in request.user.profile.get_active_stores(flat=True):
            messages.error(request, 'You don\'t have access to the <b>{}</b> store'.format(request.GET['shop']))

        return HttpResponseRedirect('/')
    else:
        user = store.user
        user.backend = settings.AUTHENTICATION_BACKENDS[0]

        user_login(request, user)

        return HttpResponseRedirect('/')


@login_required
def install(request, store):
    if not store.endswith('myshopify.com'):
        store = '{}.myshopify.com'.format(store)

    user = request.user

    if user.is_subuser:
        messages.error(request, 'Sub-Users can not add new stores.')
        return HttpResponseRedirect('/')

    can_add, total_allowed, user_count = user.profile.can_add_store()

    if not can_add:
        if user.profile.plan.is_free and (not user.is_stripe_customer() or user.stripe_customer.can_trial):
            messages.error(request, 'Please Activate your account first by visiting <a href="{}">Profile page</a>'.format(
                request.build_absolute_uri('/user/profile#plan')))
        else:
            messages.error(
                request,
                'Your plan does not support connecting another Shopify store. '
                'Please <a href="mailto:support@shopifiedapp.com">contact support</a> to learn how to connect more stores.')

        return HttpResponseRedirect('/')

    state = get_random_string(16)
    request.session['shopify_state'] = state
    shopify = shopify_session(request, state=state)
    authorization_url, state = shopify.authorization_url(AUTHORIZATION_URL.format(store))

    return HttpResponseRedirect(authorization_url)


@login_required
def callback(request):
    verify_shopify_webhook(request)
    if request.session.get('shopify_state') != request.GET['state']:
        raise PermissionDenied('State not matching')

    shop = request.GET['shop']

    user = request.user
    shopify = shopify_session(request)

    token = shopify.fetch_token(
        token_url=TOKEN_URL.format(shop),
        client_secret=settings.SHOPIFY_API_SECRET,
        code=request.GET['code'])

    try:
        store = ShopifyStore.objects.get(user=user, shop=shop, version=2, is_active=True)

        store.api_url = 'https://:{}@{}'.format(token['access_token'], shop)
        store.access_token = token['access_token']
        store.scope = token['access_token'][0]
        store.save()

    except ShopifyStore.DoesNotExist:
        can_add, total_allowed, user_count = user.profile.can_add_store()

        if not can_add:
            if user.profile.plan.is_free and (not user.is_stripe_customer() or user.stripe_customer.can_trial):
                messages.error(
                    request,
                    'Please Activate your account first by visiting:\n{}').format(
                    request.build_absolute_uri('/user/profile#plan'))
            else:
                messages.error(
                    request,
                    'Your plan does not support connecting another Shopify store. '
                    'Please contact support@shopifiedapp.com to learn how to connect more stores.')

            return HttpResponseRedirect('/')

        store = ShopifyStore(
            user=user, shop=shop, version=2,
            access_token=token['access_token'],
            scope=token['access_token'][0])

        user.can_add(store)

        try:
            store.api_url = 'https://:{}@{}'.format(token['access_token'], shop)
            store.title = store.get_info['name']

        except:
            return JsonResponse({'error': 'Shopify Store link is not correct.'}, status=500)

        store.save()

        attach_webhooks(store)

        messages.success(request, 'Your store <b>{}</b> has been added!'.format(store.title))

    return HttpResponseRedirect('/')
