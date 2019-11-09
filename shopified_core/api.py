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
from groovekart_core.api import GrooveKartApi

from leadgalaxy.models import ShopifyStore, ShopifyOrderTrack
from commercehq_core.models import CommerceHQStore, CommerceHQOrderTrack
from woocommerce_core.models import WooStore, WooOrderTrack
from gearbubble_core.models import GearBubbleStore, GearBubbleOrderTrack
from groovekart_core.models import GrooveKartStore, GrooveKartOrderTrack

from .mixins import ApiResponseMixin

from . import utils as core_utils
from . import permissions


class ShopifiedApi(ApiResponseMixin, View):
    login_non_required = ['login', 'extension-settings']

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
                        return self.api_error('Zapier integration requires a Dropified Premier account, '
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

        for i in user.profile.get_gkart_stores():
            stores.append({
                'id': i.id,
                'name': i.title,
                'type': 'gkart',
                'url': i.get_admin_url()
            })

        return JsonResponse(stores, safe=False)

    def post_store_order(self, request, user, data):
        for store_info, idx in list(data.items()):

            store_id, store_type = store_info.split(',')

            if store_type == 'shopify':
                store_model = ShopifyStore
            elif store_type == 'chq':
                store_model = CommerceHQStore
            elif store_type == 'woo':
                store_model = WooStore
            elif store_type == 'gear':
                store_model = GearBubbleStore
            elif store_type == 'gkart':
                store_model = GrooveKartStore

            store = store_model.objects.get(id=store_id)
            permissions.user_can_edit(user, store)

            store.list_index = core_utils.safe_int(idx, 0)
            store.save()

        return self.api_success()

    def post_quick_save(self, request, user, data):
        shopify_count = user.profile.get_shopify_stores().count()
        chq_count = user.profile.get_chq_stores().count()
        woo_count = user.profile.get_woo_stores().count()
        gear_count = user.profile.get_gear_stores().count()
        gkart_count = user.profile.get_gkart_stores().count()

        self.request_kwargs['target'] = 'save-for-later'

        if user.get_config('_quick_save_limit'):
            if cache.get('quick_save_limit_{}'.format(user.id)):
                return JsonResponse({'status': 'ok', 'product': {'url': '/'}})
            else:
                cache.set('quick_save_limit_{}'.format(user.id), True, timeout=user.get_config('_quick_save_limit', 5))

        other_stores_empty = woo_count == 0 and chq_count == 0 and gear_count == 0 and gkart_count == 0

        if shopify_count > 0 or other_stores_empty:
            return ShopifyStoreApi.as_view()(request, **self.request_kwargs)
        elif chq_count > 0:
            return CHQStoreApi.as_view()(request, **self.request_kwargs)
        elif woo_count > 0:
            return WooStoreApi.as_view()(request, **self.request_kwargs)
        elif gear_count > 0:
            return GearBubbleApi.as_view()(request, **self.request_kwargs)
        else:
            return GrooveKartApi.as_view()(request, **self.request_kwargs)

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
            order_tracks = core_utils.using_replica(ShopifyOrderTrack) \
                .filter(store__in=store_ids) \
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
            order_tracks = core_utils.using_replica(CommerceHQOrderTrack) \
                .filter(store__in=store_ids) \
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
            order_tracks = core_utils.using_replica(WooOrderTrack) \
                .filter(store__in=store_ids) \
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
            order_tracks = core_utils.using_replica(GearBubbleOrderTrack) \
                .filter(store__in=store_ids) \
                .filter(created_at__gte=since) \
                .filter(source_tracking='') \
                .exclude(source_status='FINISH') \
                .filter(hidden=False) \
                .defer('data') \
                .order_by('created_at')

            if data.get('store'):
                order_tracks = order_tracks.filter(store=data.get('store'))

            orders.extend(core_utils.serializers_orders_track(order_tracks, 'gear'))

        # GrooveKart
        store_ids = list(user.profile.get_gkart_stores(flat=True))
        if store_ids:
            order_tracks = core_utils.using_replica(GrooveKartOrderTrack) \
                .filter(store__in=store_ids) \
                .filter(created_at__gte=since) \
                .filter(source_tracking='') \
                .exclude(source_status='FINISH') \
                .filter(hidden=False) \
                .defer('data') \
                .order_by('created_at')

            if data.get('store'):
                order_tracks = order_tracks.filter(store=data.get('store'))

            orders.extend(core_utils.serializers_orders_track(order_tracks, 'gkart'))

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

    def get_can(self, request, user, data):
        if not user.is_authenticated:
            return self.api_error('Logging is required', status=403)
        else:
            perm = request.GET.get('perm')
            if user.can(perm):
                try:
                    plan = {'plan_id': user.profile.plan.id,
                            'slug': user.profile.plan.slug,
                            'title': user.profile.plan.title}
                except:
                    plan = None
                return JsonResponse({
                    'user_id': user.id,
                    'username': user.username,
                    'email': user.email,
                    'plan': plan
                })
            else:
                return self.api_error('Permission denied', status=403)

    def get_extension_settings(self, request, user, data):
        subid = 'aliexpress'

        if user:
            if not user.profile.plan.is_free:
                return JsonResponse({
                    'status': 'ok'
                })

            subid = f'r{user.id}'

        return JsonResponse({
            'ptr': 'https://',
            'base': 'alitems.com',
            'sid': f'/g/{settings.DROPIFIED_ADMITAD_ID}/?subid={subid}&ulp=',
            'mch': r"^https://.+\.aliexpress\.com/item/",
            'ematch': r"(aff_platform=|alitems\.com)",
            'status': 'ok'
        })
