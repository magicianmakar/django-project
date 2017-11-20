import copy
import traceback

from django.conf import settings
from django.contrib.auth import login as user_login
from django.contrib.auth import logout as user_logout
from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from django.core import serializers
from django.core.cache import cache
from django.core.exceptions import PermissionDenied
from django.core.validators import validate_email, ValidationError
from django.http import JsonResponse
from django.views.generic import View

import requests
import arrow
from raven.contrib.django.raven_compat.models import client as raven_client

from leadgalaxy.api import ShopifyStoreApi
from commercehq_core.api import CHQStoreApi
from woocommerce_core.api import WooStoreApi

from leadgalaxy.models import ShopifyOrderTrack
from commercehq_core.models import CommerceHQOrderTrack

from .mixins import ApiResponseMixin
from .exceptions import ApiLoginException

import utils as core_utils


class ShopifiedApi(ApiResponseMixin, View):
    supported_stores = [
        'all',      # Common endpoint
        'shopify',  # Shopify Stores
        'chq',      # CommerceHQ Stores
        'woo',      # WooCommerce Stores
    ]

    default = {
        'store_type': 'shopify',
        'version': 1
    }

    def dispatch(self, request, *args, **kwargs):
        for k, v in self.default.items():
            if not kwargs.get(k):
                kwargs[k] = v

        try:
            if kwargs['store_type'] not in self.supported_stores:
                return self.http_method_not_allowed(request, *args, **kwargs)

            method_names = [
                self.method_name(request.method, kwargs['store_type'], kwargs['target']),
                self.method_name(request.method, kwargs['target'])
            ]

            for method_name in method_names:
                handler = getattr(self, method_name, None)

                if handler:
                    return handler(request, **kwargs)

            if kwargs['store_type'] == 'shopify':
                return ShopifyStoreApi.as_view()(request, *args, **kwargs)
            elif kwargs['store_type'] == 'chq':
                return CHQStoreApi.as_view()(request, *args, **kwargs)
            elif kwargs['store_type'] == 'woo':
                return WooStoreApi.as_view()(request, *args, **kwargs)
            else:
                raise Exception("Unknown Store Type")

        except PermissionDenied as e:
            reason = e.message if e.message else "You don't have permission to perform this action"
            return self.api_error('Permission Denied: %s' % reason, status=403)

        except requests.Timeout:
            raven_client.captureException()
            return self.api_error('API Request Timeout', status=501)

        except ApiLoginException as e:
            return self.api_error(e.description(), status=401)

        except:
            if settings.DEBUG:
                traceback.print_exc()

            raven_client.captureException()

            return self.api_error('Internal Server Error')

    def post_login(self, request, **kwargs):
        data = self.request_data(request)

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
            username = User.objects.get(email__iexact=email).username
        except:
            return self.api_error('Invalid email or password')

        user = authenticate(username=username, password=password)
        if user is not None:
            if user.is_active:
                if request.user.is_authenticated():
                    if user != request.user:
                        user_logout(request)
                        user_login(request, user)
                else:
                    user_login(request, user)

                return JsonResponse({
                    'token': '',
                    'user': {
                        'id': user.id,
                        'username': user.username,
                        'email': user.email
                    }
                }, safe=False)

        return self.api_error('Invalid Email or password')

    def get_me(self, request, **kwargs):
        if not request.user.is_authenticated():
            return self.api_error('Logging is required', status=403)
        else:
            return JsonResponse({
                'id': request.user.id,
                'username': request.user.username,
                'email': request.user.email
            })

    def get_all_stores(self, request, target, store_type, version):
        stores = []
        user = self.get_user(request, assert_login=True)
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

        return JsonResponse(stores, safe=False)

    def post_quick_save(self, request, **kwargs):
        user = self.get_user(request, assert_login=True)

        chq_count = user.profile.get_chq_stores().count()
        shopify_count = user.profile.get_shopify_stores().count()

        kwargs['target'] = 'save-for-later'

        if user.get_config('_quick_save_limit'):
            if cache.get('quick_save_limit_{}'.format(user.id)):
                return JsonResponse({'status': 'ok', 'product': {'url': '/'}})
            else:
                cache.set('quick_save_limit_{}'.format(user.id), True, timeout=user.get_config('_quick_save_limit', 5))

        if not chq_count or (chq_count and shopify_count):
            return ShopifyStoreApi.as_view()(request, **kwargs)
        else:
            return CHQStoreApi.as_view()(request, **kwargs)

    def get_all_orders_sync(self, request, **kwargs):
        user = self.get_user(request, assert_login=True)
        data = self.request_data(request)

        if not user.can('orders.use'):
            return self.api_error('Order is not included in your account', status=402)

        orders = []

        since_key = 'sync_since_{}'.format(user.id)
        all_orders = cache.get(since_key) is None

        if core_utils.safeInt(data.get('since')) and not all_orders:
            since = arrow.get(data.get('since')).datetime
        else:
            since = arrow.now().replace(days=-30).datetime
            cache.set(since_key, arrow.utcnow().timestamp, timeout=86400)

        # Shopify
        fields = ['id', 'order_id', 'line_id', 'source_id', 'source_status', 'source_tracking', 'created_at', 'updated_at']
        order_tracks = ShopifyOrderTrack.objects.filter(user=user.models_user) \
                                                .filter(created_at__gte=since) \
                                                .filter(source_tracking='') \
                                                .exclude(shopify_status='fulfilled') \
                                                .exclude(source_status='FINISH') \
                                                .filter(hidden=False) \
                                                .only(*fields) \
                                                .order_by('created_at')

        if user.is_subuser:
            order_tracks = order_tracks.filter(store__in=user.profile.get_shopify_stores(flat=True))

        if data.get('store'):
            order_tracks = order_tracks.filter(store=data.get('store'))

        for i in serializers.serialize('python', order_tracks, fields=fields):
            fields = i['fields']
            fields['id'] = i['pk']
            fields['store_type'] = 'shopify'

            if fields['source_id'] and ',' in fields['source_id']:
                for j in fields['source_id'].split(','):
                    order_fields = copy.deepcopy(fields)
                    order_fields['source_id'] = j
                    order_fields['bundle'] = True
                    orders.append(order_fields)
            else:
                orders.append(fields)

        # CommerceHQ
        fields = ['id', 'order_id', 'line_id', 'source_id', 'source_status', 'source_tracking', 'created_at']
        order_tracks = CommerceHQOrderTrack.objects.filter(user=user.models_user) \
                                                   .filter(created_at__gte=since) \
                                                   .filter(source_tracking='') \
                                                   .exclude(source_status='FINISH') \
                                                   .filter(hidden=False) \
                                                   .defer('data') \
                                                   .order_by('created_at')

        if user.is_subuser:
            order_tracks = order_tracks.filter(store__in=user.profile.get_chq_stores(flat=True))

        if data.get('store'):
            order_tracks = order_tracks.filter(store=data.get('store'))

        for i in serializers.serialize('python', order_tracks, fields=fields):
            fields = i['fields']
            fields['id'] = i['pk']
            fields['store_type'] = 'chq'

            if fields['source_id'] and ',' in fields['source_id']:
                for j in fields['source_id'].split(','):
                    order_fields = copy.deepcopy(fields)
                    order_fields['source_id'] = j
                    order_fields['bundle'] = True
                    orders.append(order_fields)
            else:
                orders.append(fields)

        return self.api_success({
            'orders': orders,
            'all_orders': all_orders,
            'date': arrow.utcnow().timestamp
        })
