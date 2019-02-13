from django.conf import settings
from django.contrib.auth import login as user_login
from django.contrib.auth import logout as user_logout
from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.validators import validate_email, ValidationError
from django.http import JsonResponse
from django.views.generic import View

import arrow
from raven.contrib.django.raven_compat.models import client as raven_client

from leadgalaxy.api import ShopifyStoreApi
from commercehq_core.api import CHQStoreApi
from woocommerce_core.api import WooStoreApi
from gearbubble_core.api import GearBubbleApi

from leadgalaxy.models import ShopifyOrderTrack
from commercehq_core.models import CommerceHQOrderTrack
from woocommerce_core.models import WooOrderTrack
from gearbubble_core.models import GearBubbleOrderTrack

from .mixins import ApiResponseMixin

import utils as core_utils


class ShopifiedApi(ApiResponseMixin, View):

    def post_login(self, request, user, data):
        email = data.get('username')
        password = data.get('password')

        if not email or not password:
            return self.api_error('Email or password are not set', status=403)

        try:
            validate_email(email)
        except ValidationError:
            return self.api_error('Invalid email address', status=403)

        if core_utils.login_attempts_exceeded(email):
            unlock_email = core_utils.unlock_account_email(email)

            raven_client.context.merge(raven_client.get_data_from_request(request))
            raven_client.captureMessage('Maximum login attempts reached',
                                        extra={'email': email, 'from': 'API', 'unlock_email': unlock_email},
                                        level='warning')

            return self.api_error('You have reached the maximum login attempts.\nPlease try again later.', status=403)

        try:
            username = User.objects.get(email__iexact=email, profile__shopify_app_store=False).username
        except:
            return self.api_error('Invalid email or password')

        user = authenticate(username=username, password=password)
        if user is not None:
            if user.is_active:
                if request.user.is_authenticated:
                    if user != request.user:
                        user_logout(request)
                        user_login(request, user)
                else:
                    user_login(request, user)

                if request.GET.get('provider') == 'zapier':
                    if not user.can('zapier.use'):
                        url = 'https://app.dropified.com/user/profile#plan'
                        return self.api_error('Zapier integration requires a Dropified Premier account, ' +
                                              'please visit {} to upgrade your plan.'.format(url),
                                              status=403)

                token = user.get_access_token()

                core_utils.login_attempts_reset(email)

                return JsonResponse({
                    'token': token,
                    'user': {
                        'id': user.id,
                        'username': user.username,
                        'email': user.email
                    }
                }, safe=False)

        return self.api_error('Invalid Email or password')

    def post_register(self, request, user, data):
        return self.api_error('Please Visit Dropified Website to register a new account:\n\n'
                              '{}'.format(core_utils.app_link('accounts/register')), status=501)

    def get_me(self, request, user, data):
        if not user.is_authenticated:
            return self.api_error('Logging is required', status=403)
        else:
            return JsonResponse({
                'id': user.id,
                'username': user.username,
                'email': user.email
            })

    def get_stores(self, request, user, data):
        stores = []
        for i in user.profile.get_shopify_stores():
            stores.append({
                'id': i.id,
                'name': i.title,
                'type': 'shopify',
                'url': i.get_link(api=False)
            })

        for i in user.profile.get_chq_stores():
            stores.append({
                'id': i.id,
                'name': i.title,
                'type': 'chq',
                'url': i.get_admin_url()
            })

        for i in user.profile.get_woo_stores():
            stores.append({
                'id': i.id,
                'name': i.title,
                'type': 'woo',
                'url': i.get_admin_url()
            })

        for i in user.profile.get_gear_stores():
            stores.append({
                'id': i.id,
                'name': i.title,
                'type': 'gear',
                'url': i.get_admin_url()
            })

        return JsonResponse(stores, safe=False)

    def post_quick_save(self, request, user, data):
        woo_count = user.profile.get_woo_stores().count()
        chq_count = user.profile.get_chq_stores().count()
        gear_count = user.profile.get_gear_stores().count()
        shopify_count = user.profile.get_shopify_stores().count()

        self.request_kwargs['target'] = 'save-for-later'

        if user.get_config('_quick_save_limit'):
            if cache.get('quick_save_limit_{}'.format(user.id)):
                return JsonResponse({'status': 'ok', 'product': {'url': '/'}})
            else:
                cache.set('quick_save_limit_{}'.format(user.id), True, timeout=user.get_config('_quick_save_limit', 5))

        other_stores_empty = woo_count == 0 and chq_count == 0 and gear_count == 0

        if shopify_count > 0 or other_stores_empty:
            return ShopifyStoreApi.as_view()(request, **self.request_kwargs)
        elif chq_count > 0:
            return CHQStoreApi.as_view()(request, **self.request_kwargs)
        elif woo_count > 0:
            return WooStoreApi.as_view()(request, **self.request_kwargs)
        else:
            return GearBubbleApi.as_view()(request, **self.request_kwargs)

    def get_orders_sync(self, request, user, data):
        if not user.can('orders.use'):
            return self.api_error('Order is not included in your account', status=402)

        orders = []

        since_key = 'sync_since_{}'.format(user.id)
        all_orders = cache.get(since_key) is None

        if core_utils.safe_int(data.get('since')) and not all_orders:
            since = arrow.get(data.get('since')).datetime
        else:
            since = arrow.now().replace(days=-30).datetime
            cache.set(since_key, arrow.utcnow().timestamp, timeout=86400)

        # Shopify
        store_ids = list(user.profile.get_shopify_stores(flat=True))
        if store_ids:
            order_tracks = ShopifyOrderTrack.objects.filter(store__in=store_ids) \
                                                    .filter(created_at__gte=since) \
                                                    .filter(source_tracking='') \
                                                    .filter(shopify_status='') \
                                                    .exclude(source_status='FINISH') \
                                                    .filter(hidden=False) \
                                                    .only(*core_utils.serializers_orders_fields()) \
                                                    .order_by('created_at')

            if data.get('store'):
                order_tracks = order_tracks.filter(store=data.get('store'))

            orders.extend(core_utils.serializers_orders_track(order_tracks, 'shopify'))

        # CommerceHQ
        store_ids = list(user.profile.get_chq_stores(flat=True))
        if store_ids:
            order_tracks = CommerceHQOrderTrack.objects.filter(store__in=store_ids) \
                                                       .filter(created_at__gte=since) \
                                                       .filter(source_tracking='') \
                                                       .exclude(source_status='FINISH') \
                                                       .filter(hidden=False) \
                                                       .defer('data') \
                                                       .order_by('created_at')

            if data.get('store'):
                order_tracks = order_tracks.filter(store=data.get('store'))

            orders.extend(core_utils.serializers_orders_track(order_tracks, 'chq'))

        # WooCommerce
        store_ids = list(user.profile.get_woo_stores(flat=True))
        if store_ids:
            order_tracks = WooOrderTrack.objects.filter(store__in=store_ids) \
                                                .filter(created_at__gte=since) \
                                                .filter(source_tracking='') \
                                                .exclude(source_status='FINISH') \
                                                .filter(hidden=False) \
                                                .defer('data') \
                                                .order_by('created_at')

            if data.get('store'):
                order_tracks = order_tracks.filter(store=data.get('store'))

            orders.extend(core_utils.serializers_orders_track(order_tracks, 'woo'))

        # GearBubble
        store_ids = list(user.profile.get_gear_stores(flat=True))
        if store_ids:
            order_tracks = GearBubbleOrderTrack.objects.filter(store__in=store_ids) \
                                                       .filter(created_at__gte=since) \
                                                       .filter(source_tracking='') \
                                                       .exclude(source_status='FINISH') \
                                                       .filter(hidden=False) \
                                                       .defer('data') \
                                                       .order_by('created_at')

            if data.get('store'):
                order_tracks = order_tracks.filter(store=data.get('store'))

            orders.extend(core_utils.serializers_orders_track(order_tracks, 'gear'))

        return self.api_success({
            'orders': orders,
            'all_orders': all_orders,
            'date': arrow.utcnow().timestamp
        })

    def get_ali_login(self, request, user, data):
        # Ensure the Dropified Secret key match with our app's setting key
        if settings.API_SECRECT_KEY != request.META.get('HTTP_X_DROPIFIED_SECRET'):
            return self.api_error('Wrong Dropified API Key')

        aliexpress_email = user.get_config('ali_email')
        if not aliexpress_email:
            return self.api_error('Aliexpress email is not set')

        from shopified_core.encryption import get_aliexpress_password

        return self.api_success({
            'password': get_aliexpress_password(user, aliexpress_email)
        })
