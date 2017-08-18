# -*- coding: utf-8 -*-

import traceback
import urlparse
import copy

from django.contrib.auth import authenticate, login
from django.core import serializers
from django.core.cache import cache
from django.core.exceptions import PermissionDenied
from django.core.urlresolvers import reverse
from django.db import transaction
from django.db.models import F
from django.forms.models import model_to_dict
from django.http import HttpResponse, HttpResponseRedirect, Http404
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.template.defaultfilters import truncatewords
from django.utils import timezone
from django.views.generic import View

from raven.contrib.django.raven_compat.models import client as raven_client

from shopified_core import permissions
from shopified_core.mixins import ApiResponseMixin
from shopified_core.shipping_helper import get_counrties_list
from shopified_core.utils import (
    app_link,
    send_email_from_template,
    version_compare,
    order_data_cache,
    orders_update_limit,
    order_phone_number
)

from shopify_orders import utils as shopify_orders_utils
from shopify_orders.tasks import fulfill_shopify_order_line
from shopify_orders.models import (
    ShopifyOrder,
    ShopifySyncStatus,
)
from dropwow_core.models import DropwowAccount, DropwowOrderStatus
from dropwow_core.utils import fulfill_dropwow_order

import tasks
import utils
from .forms import *
from .models import *
from .templatetags.template_helper import shopify_image_thumb, money_format


class ShopifyStoreApi(ApiResponseMixin, View):
    http_method_names = ['get', 'post', 'delete']

    def dispatch(self, request, *args, **kwargs):
        if request.method.lower() not in self.http_method_names:
            raven_client.captureMessage('Unsupported Request Method', extra={'method': request.method})
            return self.http_method_not_allowed(request, *args, **kwargs)

        return self.proccess_api(request, **kwargs)

    def proccess_api(self, request, target, store_type, version):
        self.target = target
        self.data = self.request_data(request)

        # Methods that doesn't require login or perform login differently (from json data)
        assert_login = target not in ['shipping-aliexpress']

        user = self.get_user(request, assert_login=assert_login)
        if user:
            raven_client.user_context({
                'id': user.id,
                'username': user.username,
                'email': user.email
            })

            extension_version = request.META.get('HTTP_X_EXTENSION_VERSION')
            if extension_version:
                user.set_config('extension_version', extension_version)

        method_name = self.method_name(request.method, target)
        handler = getattr(self, method_name, None)

        if not handler:
            if settings.DEBUG:
                print 'Method Not Found:', method_name

            raven_client.captureMessage('Non-handled endpoint', extra={'method': method_name})
            return self.api_error('Non-handled endpoint', status=405)

        res = handler(request, user, self.data)
        if res is None:
            res = self.response

        if res is None:
            raven_client.captureMessage('API Response is empty')
            res = self.api_error('Internal Server Error', 500)

        return res

    def post_register(self, request, user, data):
        return self.api_error('Please Visit Dropified Website to register a new account:\n\n'
                              '{}'.format(app_link('accounts/register')), status=501)

    def get_stores(self, request, user, data):
        stores = []
        for i in user.profile.get_shopify_stores():
            stores.append({
                'id': i.id,
                'name': i.title,
                'type': 'shopify',
                'url': i.get_link(api=False)
            })

        if data.get('all'):
            for i in user.profile.get_chq_stores():
                stores.append({
                    'id': i.id,
                    'name': i.title,
                    'type': 'chq',
                    'url': i.get_admin_url()
                })

        return JsonResponse(stores, safe=False)

    def post_delete_store(self, request, user, data):
        store = ShopifyStore.objects.get(id=data.get('store'), user=user)
        permissions.user_can_delete(user, store)  # Sub users can't delete a store

        store.is_active = False
        store.uninstalled_at = timezone.now()
        store.save()

        if store.version == 2:
            try:
                utils.detach_webhooks(store, delete_too=True)
            except:
                pass

            try:
                requests.delete(store.get_link('/admin/api_permissions/current.json', api=True)) \
                        .raise_for_status()

            except requests.exceptions.HTTPError as e:
                if e.response.status_code not in [401, 402, 403, 404]:
                    raise
        else:
            utils.detach_webhooks(store, delete_too=True)

        stores = []
        for i in user.profile.get_shopify_stores():
            stores.append({
                'id': i.id,
                'name': i.title,
                'url': i.get_api_url(hide_keys=True)
            })

        return JsonResponse(stores, safe=False)

    def post_update_store(self, request, user, data):
        store = ShopifyStore.objects.get(id=data.get('store'))
        permissions.user_can_edit(user, store)

        store_title = data.get('title')
        store_api_url = data.get('url')
        api_url_changes = (store.api_url != data.get('url'))

        store_check = ShopifyStore(title=store_title, api_url=store_api_url, user=user)  # Can't be a sub user
        try:
            info = store_check.get_info
            if not store_title:
                store_title = info['name']
        except:
            return self.api_error('Shopify Store link is not correct.', status=500)

        if api_url_changes:
            utils.detach_webhooks(store, delete_too=True)

        store.title = store_title
        store.api_url = store_api_url
        store.save()

        if api_url_changes:
            utils.attach_webhooks(store)

        return self.api_success()

    def get_custom_tracking_url(self, request, user, data):
        store = ShopifyStore.objects.get(id=data.get('store'))
        permissions.user_can_view(user, store)

        custom_tracking = None
        aftership_domain = user.models_user.get_config('aftership_domain')
        if aftership_domain and type(aftership_domain) is dict:
            custom_tracking = aftership_domain.get(str(store.id))

        return self.api_success({
            'tracking_url': custom_tracking,
            'store': store.id
        })

    def post_custom_tracking_url(self, request, user, data):
        store = ShopifyStore.objects.get(id=data.get('store'))
        permissions.user_can_edit(user, store)

        if not user.can('edit_settings.sub'):
            raise PermissionDenied()

        aftership_domain = user.models_user.get_config('aftership_domain')
        if not aftership_domain:
            aftership_domain = {}
        elif type(aftership_domain) is not dict:
            raise Exception('Custom domains is not a dict')

        if data.get('tracking_url'):
            aftership_domain[str(store.id)] = data.get('tracking_url')
        else:
            if str(store.id) in aftership_domain:
                del aftership_domain[str(store.id)]

        user.models_user.set_config('aftership_domain', aftership_domain)

        return self.api_success()

    def post_store_order(self, request, user, data):
        for store, idx in data.iteritems():
            store = ShopifyStore.objects.get(id=store)
            permissions.user_can_edit(user, store)

            store.list_index = utils.safeInt(idx, 0)
            store.save()

        return self.api_success()

    def get_store_verify(self, request, user, data):
        try:
            store = ShopifyStore.objects.get(id=data.get('store'))
            permissions.user_can_view(user, store)

        except ShopifyStore.DoesNotExist:
            return self.api_error('Store not found', status=404)

        try:
            info = store.get_info

            if store.version == 1:
                ok, missing_perms = utils.verify_shopify_permissions(store)
                if not ok:
                    return self.api_error(
                        'The following permissions are missing: \n{}\n\n'
                        'You can find instructions to fix this issue here:\n{}'
                        .format('\n'.join(missing_perms), app_link('pages/fix-private-app-permissions')), status=403)

            return self.api_success({'store': info['name']})

        except:
            if settings.DEBUG:
                traceback.print_exc()

            return self.api_error('Shopify Store link is not correct.', status=500)

    def get_product(self, request, user, data):
        try:
            product = ShopifyProduct.objects.get(id=data.get('product'))
            permissions.user_can_view(user, product)

        except ShopifyProduct.DoesNotExist:
            return self.api_error('Product not found')

        return JsonResponse(json.loads(product.data), safe=False)

    def get_products_info(self, request, user, data):
        products = {}
        for p in data.getlist('products[]'):
            try:
                product = ShopifyProduct.objects.get(id=p)
                permissions.user_can_view(user, product)

                products[p] = json.loads(product.data)
            except:
                return self.api_error('Product not found')

        return JsonResponse(products, safe=False)

    def post_shopify(self, request, user, data):
        if data.get('store'):
            store = ShopifyStore.objects.get(pk=data['store'])

            if self.target == 'save-for-later' and not user.can('save_for_later.sub', store):
                raise PermissionDenied()
            elif self.target in ['shopify', 'shopify-update'] and not user.can('send_to_shopify.sub', store):
                raise PermissionDenied()

        delayed = data.get('b')

        if not delayed or self.target == 'save-for-later':
            result = tasks.export_product(data, self.target, user.id)
            result = utils.fix_product_url(result, request)

            return JsonResponse(result, safe=False)
        else:
            task = tasks.export_product.apply_async(args=[data, self.target, user.id], expires=60)

            return self.api_success({'id': str(task.id)})

    def post_save_for_later_products(self, request, user, data):
        self.target = 'save-for-later'
        products = {}
        for p in data.get('products', []):
            result = self.post_shopify(request, user, p)
            result = json.loads(result.content)
            id = result['product']['id']
            product = ShopifyProduct.objects.get(id=id)
            products[p['original_id']] = json.loads(product.data)
            products[p['original_id']]['id'] = id
        return JsonResponse(products, safe=False)

    def post_shopify_update(self, request, user, data):
        return self.post_shopify(request, user, data)

    def post_save_for_later(self, request, user, data):
        return self.post_shopify(request, user, data)

    def get_export_product(self, request, user, data):
        task = tasks.export_product.AsyncResult(data.get('id'))
        count = utils.safeInt(data.get('count'))

        if count == 60:
            raven_client.context.merge(raven_client.get_data_from_request(request))
            raven_client.captureMessage('Celery Task is taking too long.', level='warning')

        if count > 120 and count < 125:
            raven_client.captureMessage('Terminate Celery Task.',
                                        extra={'task': data.get('id')},
                                        level='warning')

            task.revoke(terminate=True)
            return self.api_error('Export Error', status=500)

        if count >= 125:
            return self.api_error('Export Error', status=404)

        if not task.ready():
            return self.api_success({
                'ready': False
            })
        else:
            data = task.result
            data = utils.fix_product_url(data, request)

            if 'product' in data:
                return self.api_success({
                    'ready': True,
                    'data': data
                })
            else:
                if type(data) is not dict:
                    if isinstance(data, Exception) or isinstance(data, basestring):
                        data = {
                            'error': 'Export is taking too long'
                        }
                    else:
                        data = {
                            'error': 'Shopify Export Error.'
                        }

                return JsonResponse(data, safe=False, status=500)

    def post_product_delete(self, request, user, data):
        try:
            product = ShopifyProduct.objects.get(id=data.get('product'))
            permissions.user_can_delete(user, product)
        except ShopifyProduct.DoesNotExist:
            return self.api_error('Product does not exists', status=404)

        if not user.can('delete_products.sub', product.store):
            raise PermissionDenied()

        product.userupload_set.update(product=None)
        product.delete()

        if product.shopify_id:
            tasks.update_product_connection.delay(product.store.id, product.shopify_id)

        return self.api_success()

    def post_bulk_edit(self, request, user, data):
        for p in data.getlist('product'):
            product = ShopifyProduct.objects.get(id=p)
            permissions.user_can_edit(user, product)

            product_data = json.loads(product.data)

            product_data['title'] = data.get('title[%s]' % p)
            product_data['tags'] = data.get('tags[%s]' % p)
            product_data['price'] = utils.safeFloat(data.get('price[%s]' % p))
            product_data['compare_at_price'] = utils.safeFloat(data.get('compare_at[%s]' % p))
            product_data['type'] = data.get('type[%s]' % p)
            product_data['weight'] = data.get('weight[%s]' % p)

            product.data = json.dumps(product_data)
            product.save()

        return self.api_success()

    def post_bulk_edit_connected(self, request, user, data):
        try:
            store = ShopifyStore.objects.get(id=data.get('store'))
            permissions.user_can_view(user, store)
        except ShopifyStore.DoesNotExist:
            return self.api_error('Store not found', status=404)

        task = tasks.bulk_edit_products.apply_async(
            args=[store.id, data['products']],
            queue='priority_high')

        return self.api_success({'task': task.id})

    def get_product_shopify_id(self, request, user, data):
        ids = []
        products = data.get('product').split(',')
        for p in products:
            product = ShopifyProduct.objects.get(id=p)
            shopify_id = product.get_shopify_id()
            if shopify_id and shopify_id not in ids:
                ids.append(shopify_id)

        return self.api_success({'ids': ids})

    def post_product_edit(self, request, user, data):
        products = []
        for p in data.getlist('products[]'):
            product = ShopifyProduct.objects.get(id=p)
            permissions.user_can_edit(user, product)

            product_data = json.loads(product.data)

            if 'tags' in data:
                product_data['tags'] = data.get('tags')

            if 'price' in data:
                product_data['price'] = utils.safeFloat(data.get('price'))

            if 'compare_at' in data:
                product_data['compare_at_price'] = utils.safeFloat(data.get('compare_at'))

            if 'type' in data:
                product_data['type'] = data.get('type')

            if 'weight' in data:
                product_data['weight'] = data.get('weight')

            if 'weight_unit' in data:
                product_data['weight_unit'] = data.get('weight_unit')

            products.append(product_data)

            product.data = json.dumps(product_data)
            product.save()

        return self.api_success({'products': products})

    def post_boards_add(self, request, user, data):
        if not user.can('edit_product_boards.sub'):
            raise PermissionDenied()

        can_add, total_allowed, user_count = permissions.can_add_board(user)

        if not can_add:
            return self.api_error(
                'Your current plan allow up to %d boards, currently you have %d boards.'
                % (total_allowed, user_count))

        board_name = data.get('title', '').strip()

        if not len(board_name):
            return self.api_error('Board name is required', status=501)

        board = ShopifyBoard(title=board_name, user=user.models_user)
        permissions.user_can_add(user, board)

        board.save()

        return self.api_success({
            'board': {
                'id': board.id,
                'title': board.title
            }
        })

    def post_board_add_products(self, request, user, data):
        if not user.can('edit_product_boards.sub'):
            raise PermissionDenied()

        board = ShopifyBoard.objects.get(id=data.get('board'))
        permissions.user_can_edit(user, board)

        for p in data.getlist('products[]'):
            product = ShopifyProduct.objects.get(id=p)
            permissions.user_can_edit(user, product)

            board.products.add(product)

        board.save()

        return self.api_success()

    def post_product_remove_board(self, request, user, data):
        if not user.can('edit_product_boards.sub'):
            raise PermissionDenied()

        board = ShopifyBoard.objects.get(id=data.get('board'))
        permissions.user_can_edit(user, board)

        for p in data.getlist('products[]'):
            product = ShopifyProduct.objects.get(id=p)
            permissions.user_can_edit(user, product)

            board.products.remove(product)

        board.save()

        return self.api_success()

    def post_product_board(self, request, user, data):
        if not user.can('edit_product_boards.sub'):
            raise PermissionDenied()

        product = ShopifyProduct.objects.get(id=data.get('product'))
        permissions.user_can_edit(user, product)

        if data.get('board') == '0':
            product.shopifyboard_set.clear()
            product.save()

            return self.api_success()
        else:
            board = ShopifyBoard.objects.get(id=data.get('board'))
            permissions.user_can_edit(user, board)

            board.products.add(product)
            board.save()

            return self.api_success({
                'board': {
                    'id': board.id,
                    'title': board.title
                }
            })

    def post_board_delete(self, request, user, data):
        if not user.can('edit_product_boards.sub'):
            raise PermissionDenied()

        board = ShopifyBoard.objects.get(id=data.get('board'))
        permissions.user_can_delete(user, board)

        board.delete()

        return self.api_success()

    def post_board_empty(self, request, user, data):
        if not user.can('edit_product_boards.sub'):
            raise PermissionDenied()

        board = ShopifyBoard.objects.get(id=data.get('board'))
        permissions.user_can_edit(user, board)

        board.products.clear()

        return self.api_success()

    def get_board_config(self, request, user, data):
        if not user.can('view_product_boards.sub'):
            raise PermissionDenied()

        board = ShopifyBoard.objects.get(id=data.get('board'))
        permissions.user_can_edit(user, board)

        try:
            return self.api_success({
                'title': board.title,
                'config': json.loads(board.config)
            })
        except:
            return self.api_success({
                'title': board.title,
                'config': {
                    'title': '',
                    'tags': '',
                    'type': ''
                }
            })

    def post_board_config(self, request, user, data):
        if not user.can('edit_product_boards.sub'):
            raise PermissionDenied()

        board = ShopifyBoard.objects.get(id=data.get('board'))
        permissions.user_can_edit(user, board)

        board.title = data.get('store-title')

        board.config = json.dumps({
            'title': data.get('title'),
            'tags': data.get('tags'),
            'type': data.get('type'),
        })

        board.save()

        # utils.smart_board_by_board(user.models_user, board)

        return self.api_success()

    def post_variant_image(self, request, user, data):
        try:
            store = ShopifyStore.objects.get(id=data.get('store'))
            permissions.user_can_view(user, store)

        except ShopifyStore.DoesNotExist:
            return self.api_error('Store not found', status=404)

        api_url = '/admin/variants/{}.json'.format(data.get('variant'))
        api_url = store.get_link(api_url, api=True)

        api_data = {
            "variant": {
                "id": data.get('variant'),
                "image_id": data.get('image'),
            }
        }

        requests.put(api_url, json=api_data)

        return self.api_success()

    def delete_product_image(self, request, user, data):
        store = ShopifyStore.objects.get(id=data.get('store'))
        permissions.user_can_view(user, store)

        product = utils.safeInt(data.get('product'))
        if not product:
            return self.api_error('Product Not Found', status=404)

        ShopifyProductImage.objects.filter(store=store, product=product).delete()

        return self.api_success()

    def post_clippingmagic_clean_image(self, request, user, data):
        img_url = None
        api_url = 'https://clippingmagic.com/api/v1/images'
        action = data.get('action', 'edit')
        image_id = data.get('image_id', 0)
        api_response = {}

        try:
            ClippingMagic.objects.get(user=user)
        except ClippingMagic.DoesNotExist:
            ClippingMagic.objects.create(user=request.user, remaining_credits=5)

        if user.clippingmagic.remaining_credits <= 0:
            return self.api_error('Looks like your credits have run out', status=402)

        if action == 'edit':
            res = requests.post(
                api_url,
                files={
                    'image': requests.get(data.get('image_url')).content
                },
                auth=(settings.CLIPPINGMAGIC_API_ID, settings.CLIPPINGMAGIC_API_SECRET)
            ).json()

            api_response = res.get('image', {'id': 0, 'secret': 0})

        elif action == 'done':
            img_url = requests.get(
                '{}/{}'.format(api_url, image_id),
                auth=(settings.CLIPPINGMAGIC_API_ID, settings.CLIPPINGMAGIC_API_SECRET)
            ).url

            if img_url:
                UserUpload.objects.create(
                    user=request.user.models_user,
                    product=data.get('product_id'),
                    url=img_url[:510]
                )

                user.clippingmagic.remaining_credits -= 1
                user.clippingmagic.save()
            else:
                return self.api_error('Action is not defined', status=500)

        if api_response.get('id') or img_url:
            return self.api_success({
                'image_id': api_response.get('id', 0),
                'image_secret': api_response.get('secret', 0),
                'api_id': settings.CLIPPINGMAGIC_API_ID,
                'image_url': img_url
            })
        else:
            error = res.get('error')

            if error.get('code') == 1001:
                response = ('Invalid API Keys click '
                            '<a href="/user/profile#clippingmagic">here</a> to '
                            'update your API credentials.')

            elif error.get('code') == 1008:
                response = ('Seems your trial is expired please upgrade '
                            'your account at <a href="http://clippingmagic.com/api" '
                            'target = "_blank">ClippingMagic</a>')

            else:
                response = 'ClippingMagic API Error'

            raven_client.captureMessage('ClippingMagic API Error', level='warning', extra=res)

            return self.api_error(response, status=500)

    def post_youzign_images(self, request, user, data):
        api_url = 'https://www.youzign.com/api/designs/'

        auth_detils = {
            'key': user.get_config('yz_public_key'),
            'token': user.get_config('yz_access_token'),
        }

        try:
            assert auth_detils['key'] and auth_detils['token']

            res = requests.get(api_url, params=auth_detils, headers={'User-Agent': 'Mozilla/5.0 (X11; Linux i686)'})

            res.raise_for_status()

            return self.api_success({"data": res.json()})

        except AssertionError:
            return self.api_error("Your YouZign API credentials is not set", status=402)

        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 403:
                return self.api_error("Invalid YouZign API credentials", status=403)
            else:
                raven_client.captureException()

        except Exception as e:
            raven_client.captureException()

        return self.api_error("YouZign API Error")

    def post_change_plan(self, request, user, data):
        if not user.is_superuser and not user.is_staff:
            raise PermissionDenied()

        target_user = User.objects.get(id=data.get('user'))

        if data.get('allow_trial'):
            target_user.stripe_customer.can_trial = True
            target_user.stripe_customer.save()

            AdminEvent.objects.create(
                user=user,
                target_user=target_user,
                event_type='allow_trial', data='{}')

            return self.api_success()

        if target_user.is_recurring_customer():
            return self.api_error(
                ('Plan should be changed from Stripe Dashboard:\n'
                 'https://dashboard.stripe.com/customers/{}').format(target_user.stripe_customer.customer_id),
                status=422)

        plan = GroupPlan.objects.get(id=data.get('plan'))
        try:
            profile = target_user.profile
            target_user.profile.plan = plan
        except:
            profile = UserProfile(user=target_user, plan=plan)
            profile.save()

        target_user.profile.save()

        AdminEvent.objects.create(
            user=user,
            target_user=target_user,
            event_type='change_plan',
            data=json.dumps({'new_plan': plan.title}))

        return self.api_success({
            'plan': {
                'id': plan.id,
                'title': plan.title
            }
        })

    def post_add_bundle(self, request, user, data):
        if not user.is_superuser and not user.is_staff:
            raise PermissionDenied()

        target_user = User.objects.get(id=data.get('user'))
        bundle = FeatureBundle.objects.get(id=data.get('bundle'))

        if target_user.is_subuser:
            return self.api_error('Sub User Account', status=422)

        AdminEvent.objects.create(
            user=user,
            target_user=target_user,
            event_type='add_bundle',
            data=json.dumps({'bundle': bundle.title}))

        target_user.profile.bundles.add(bundle)

        return self.api_success()

    def post_stripe_refund_charge(self, request, user, data):
        if not user.is_superuser and not user.is_staff:
            raise PermissionDenied()

        target_user = User.objects.get(id=data.get('user'))

        amount = utils.safeFloat(data.get('amount'))
        if not amount:
            return self.api_error('Invalid Refund Amount')

        charge = stripe.Charge.retrieve(id=data.get('id'))

        AdminEvent.objects.create(
            user=user,
            target_user=target_user,
            event_type='refund_charge',
            data=json.dumps({'amount': amount, 'charge': charge.id}))

        try:
            charge.refund(amount=int(amount * 100))
        except stripe.InvalidRequestError as e:
            raven_client.captureException(level='warning')
            return self.api_error(e.message)

        return self.api_success()

    def post_stripe_cancel_subscription(self, request, user, data):
        if not user.is_superuser and not user.is_staff:
            raise PermissionDenied()

        target_user = User.objects.get(id=data.get('user'))
        sub = stripe.Subscription.retrieve(id=data.get('id'))

        AdminEvent.objects.create(
            user=user,
            target_user=target_user,
            event_type='subscription_cancel',
            data=json.dumps({'subscription': sub.id}))

        sub.delete()

        return self.api_success()

    def delete_access_token(self, request, user, data):
        if not user.is_superuser:
            raise PermissionDenied()

        target_user = User.objects.get(id=data.get('user'))
        for i in target_user.accesstoken_set.all():
            i.delete()

        return self.api_success()

    def post_product_notes(self, request, user, data):
        product = ShopifyProduct.objects.get(id=data.get('product'))
        permissions.user_can_edit(user, product)

        product.notes = data.get('notes')
        product.save()

        return self.api_success()

    def post_shopify_products(self, request, user, data):
        store = utils.safeInt(data.get('store'))
        if not store:
            return self.api_error('No Store was selected', status=404)

        try:
            store = ShopifyStore.objects.get(id=store)
            permissions.user_can_view(user, store)

            page = utils.safeInt(data.get('page'), 1)
            limit = 25

            params = {
                'fields': 'id,title,image',
                'limit': limit,
                'page': page
            }

            ids = utils.get_shopify_id(data.get('query'))
            if ids:
                params['ids'] = [ids]
            else:
                params['title'] = data.get('query')

            rep = requests.get(
                url=store.get_link('/admin/products.json', api=True),
                params=params
            )

            if not rep.ok:
                return self.api_error('Shopify API Error', status=500)

            products = []
            for i in rep.json()['products']:
                if i.get('image') and i['image'].get('src'):
                    i['image']['src'] = shopify_image_thumb(i['image']['src'], size='thumb')

                products.append(i)

            if data.get('connected') or data.get('hide_connected'):
                connected = {}
                for p in store.shopifyproduct_set.filter(shopify_id__in=[i['id'] for i in products]).values_list('id', 'shopify_id'):
                    connected[p[1]] = p[0]

                for idx, i in enumerate(products):
                    products[idx]['connected'] = connected.get(i['id'])

                def connected_cmp(a, b):
                    if a['connected'] and b['connected']:
                        return a['connected'] < b['connected']
                    elif a['connected']:
                        return 1
                    elif b['connected']:
                        return -1
                    else:
                        return 0

                products = sorted(products, cmp=connected_cmp, reverse=True)

                if data.get('hide_connected'):
                    products = filter(lambda p: not p.get('connected'), products)

            return JsonResponse({
                'products': products,
                'page': page,
                'next': page + 1 if (len(products) == limit or data.get('hide_connected')) else None,
            })

        except ShopifyStore.DoesNotExist:
            return self.api_error('Store not found', status=404)

    def post_product_connect(self, request, user, data):
        product = ShopifyProduct.objects.get(id=data.get('product'))
        permissions.user_can_edit(user, product)

        store = ShopifyStore.objects.get(id=data.get('store'))
        permissions.user_can_view(user, store)

        shopify_id = utils.safeInt(data.get('shopify'))

        if shopify_id != product.shopify_id or product.store != store:
            connected_to = ShopifyProduct.objects.filter(
                store=store,
                shopify_id=shopify_id
            )

            if connected_to.exists():
                return self.api_error(
                    '\n'.join(
                        ['The selected Product is already connected to:\n'] +
                        [request.build_absolute_uri('/product/{}'.format(i))
                            for i in connected_to.values_list('id', flat=True)]),
                    status=500)

            product.store = store
            product.shopify_id = shopify_id

            # Add a supplier if there is no default one
            if not product.default_supplier:
                supplier = product.get_supplier_info()
                supplier = ProductSupplier.objects.create(
                    store=product.store,
                    product=product,
                    product_url=product.get_original_info().get('url', ''),
                    supplier_name=supplier.get('name'),
                    supplier_url=supplier.get('url'),
                    is_default=True
                )

                product.set_default_supplier(supplier)

            product.save()

            cache.delete('export_product_{}_{}'.format(product.store.id, shopify_id))
            tasks.update_product_connection.delay(product.store.id, shopify_id)

            tasks.update_shopify_product(product.store.id, shopify_id, product_id=product.id)

        return self.api_success()

    def delete_product_connect(self, request, user, data):
        product = ShopifyProduct.objects.get(id=data.get('product'))
        permissions.user_can_edit(user, product)

        shopify_id = product.shopify_id
        if shopify_id:
            product.shopify_id = 0
            product.save()

            cache.delete('export_product_{}_{}'.format(product.store.id, shopify_id))
            tasks.update_product_connection.delay(product.store.id, shopify_id)

        return self.api_success()

    def post_product_metadata(self, request, user, data):
        if not user.can('product_metadata.use'):
            return self.api_error('Your current plan doesn\'t have this feature.', status=500)

        product = ShopifyProduct.objects.get(id=data.get('product'))
        permissions.user_can_edit(user, product)

        original_link = utils.remove_link_query(data.get('original-link'))

        if 'click.aliexpress.com' in original_link.lower():
            return self.api_error('The submitted Aliexpress link will not work properly with order fulfillment')

        if not original_link:
            return self.api_error('Original Link is not set', status=500)

        try:
            store = product.store
        except:
            store = None
        if not store:
            return self.api_error('Shopify store not found', status=500)

        product.set_original_url(original_link)

        supplier_url = utils.remove_link_query(data.get('supplier-link'))

        try:
            product_supplier = ProductSupplier.objects.get(id=data.get('export'))
            permissions.user_can_edit(user, product_supplier)

            product_supplier.product = product
            product_supplier.product_url = original_link
            product_supplier.supplier_name = data.get('supplier-name')
            product_supplier.supplier_url = supplier_url
            product_supplier.notes = data.get('supplier-notes', '')
            product_supplier.save()

        except (ValueError, ProductSupplier.DoesNotExist):
            product_supplier = ProductSupplier.objects.create(
                store=store,
                product=product,
                product_url=original_link,
                supplier_name=data.get('supplier-name'),
                supplier_url=supplier_url,
                notes=data.get('supplier-notes', ''),
            )

        if not product.default_supplier_id or not data.get('export'):
            product.set_default_supplier(product_supplier)

        product.save()

        return self.api_success({
            'reload': not data.get('export')
        })

    def delete_product_metadata(self, request, user, data):
        product = ShopifyProduct.objects.get(id=data.get('product'))
        permissions.user_can_edit(user, product)

        try:
            supplier = ProductSupplier.objects.get(id=data.get('export'), product=product)
        except ProductSupplier.DoesNotExist:
            return self.api_error('Supplier not found.\nPlease reload the page and try again.')

        need_update = product.default_supplier == supplier

        supplier.delete()

        if need_update:
            other_supplier = product.get_suppliers().first()
            if other_supplier:
                product.set_original_url(other_supplier.product_url)
                product.set_default_supplier(other_supplier)
                product.save()

        return self.api_success()

    def post_product_metadata_default(self, request, user, data):
        product = ShopifyProduct.objects.get(id=data.get('product'))
        permissions.user_can_edit(user, product)

        try:
            supplier = ProductSupplier.objects.get(id=data.get('export'), product=product)
            permissions.user_can_edit(user, supplier)
        except ProductSupplier.DoesNotExist:
            return self.api_error('Supplier not found.\nPlease reload the page and try again.')

        product.set_default_supplier(supplier)

        product.set_original_url(supplier.product_url)
        product.save()

        return self.api_success()

    def post_add_user_upload(self, request, user, data):
        product = ShopifyProduct.objects.get(id=data.get('product'))
        permissions.user_can_edit(user, product)

        upload = UserUpload(user=user.models_user, product=product, url=data.get('url'))
        permissions.user_can_add(user, upload)

        upload.save()

        return self.api_success()

    def post_product_duplicate(self, request, user, data):
        product = ShopifyProduct.objects.get(id=data.get('product'))
        permissions.user_can_view(user, product)

        duplicate_product = utils.duplicate_product(product)

        return self.api_success({
            'product': {
                'id': duplicate_product.id,
                'url': reverse('product_view', args=[duplicate_product.id])
            }
        })

    def post_product_split_variants(self, request, user, data):
        product = ShopifyProduct.objects.get(id=data.get('product'))
        split_factor = data.get('split_factor')
        permissions.user_can_view(user, product)

        splitted_products = utils.split_product(product, split_factor)

        # if current product is connected, automatically connect splitted products.
        if product.shopify_id:
            for splitted_product in splitted_products:
                data = json.loads(splitted_product.data)

                variants = []
                for v in data['variants']:
                    variant = {
                        'title': v['title'],
                        'price': data['price'],
                        'compare_at_price': data['compare_at_price'],
                        'weight': data['weight'],
                        'weight_unit': data['weight_unit']
                    }

                    for i, option in enumerate(v['values']):
                        variant['option{}'.format(i)] = option

                    variants.append(variant)

                images = []
                for i in data['images']:
                    img = {'src': i}
                    img_filename = utils.hash_url_filename(i)
                    if data['variants_images'] and img_filename in data['variants_images']:
                        img['filename'] = 'v-{}__{}'.format(data['variants_images'][img_filename], img_filename)

                    images.append(img)

                req_data = {
                    'product': splitted_product.id,
                    'store': splitted_product.store_id,
                    'data': json.dumps({
                        'product': {
                            'title': data['title'],
                            'body_html': data['description'],
                            'product_type': data['type'],
                            'vendor': data['vendor'],
                            'published': data['published'],
                            'tags': data['tags'],
                            'variants': variants,
                            'options': [{'name': v['title'], 'values': v['values']} for v in data['variants']],
                            'images': images
                        }
                    })
                }

                tasks.export_product.apply_async(args=[req_data, 'shopify', user.id], expires=60)

        return self.api_success({
            'products_ids': [p.id for p in splitted_products]
        })

    def post_product_exclude(self, request, user, data):
        product = ShopifyProduct.objects.get(id=data.get('product'))
        permissions.user_can_view(user, product)

        if product.is_excluded:
            return self.api_error('Product is already excluded', status=422)

        product.is_excluded = True
        product.save()

        tasks.sync_product_exclude.delay(product.store.id, product.id)

        return self.api_success()

    def post_product_include(self, request, user, data):
        product = ShopifyProduct.objects.get(id=data.get('product'))
        permissions.user_can_view(user, product)

        if not product.is_excluded:
            return self.api_error('Product is already included', status=422)

        product.is_excluded = False
        product.save()

        tasks.sync_product_exclude.delay(product.store.id, product.id)

        return self.api_success()

    def get_user_config(self, request, user, data):
        if data.get('current'):
            profile = user.profile
        else:
            profile = user.models_user.profile

        config = profile.get_config()
        if not user.can('auto_margin.use'):
            for i in ['auto_margin', 'auto_margin_cents', 'auto_compare_at', 'auto_compare_at_cents']:
                if i in config:
                    del config[i]
        else:
            # make sure this fields are populated so the extension can display them
            for i in ['auto_margin', 'auto_margin_cents', 'auto_compare_at', 'auto_compare_at_cents']:
                if i not in config or config[i] == '%':
                    config[i] = ''

            rules = PriceMarkupRule.objects.filter(user=user.models_user)
            rules_dict = []
            for i in rules:
                i_dict = model_to_dict(i, fields='id,name,min_price,max_price,markup_type,markup_value,markup_compare_value')
                i_dict['markup_type_display'] = i.get_markup_type_display()
                rules_dict.append(i_dict)

            config['markup_rules'] = rules_dict

        if not user.can('auto_order.use'):
            for i in ['order_phone_number', 'order_custom_note', ]:
                if i in config:
                    del config[i]
        else:
            for i in ['order_phone_number', 'order_custom_note', ]:
                if i not in config:
                    config[i] = ''

        if not config.get('description_mode'):
            config['description_mode'] = 'empty'

        config['import'] = profile.import_stores()

        # Base64 encode the store import list
        config['import'] = json.dumps(config['import']).encode('base64').replace('\n', '')

        for k in config.keys():
            if (k.startswith('_') or k == 'access_token') and k not in data.get('name', ''):
                del config[k]

        extension_release = cache.get('extension_release')
        if extension_release is not None:
            config['release'] = {
                'min_version': extension_release,
                'force_update': cache.get('extension_required', False)
            }

        can_add, total_allowed, user_count = permissions.can_add_store(user)

        extra_stores = can_add and user.profile.plan.is_stripe() and \
            user.profile.get_shopify_stores().count() >= 1

        config['extra_stores'] = extra_stores

        if data.get('name'):
            named_config = {}
            for name in data.get('name').split(','):
                if name in config:
                    named_config[name] = config[name]

            config = named_config

        # Auto Order Timeout
        config['ot'] = {
            #  Start Auto fulfill after `t` is elapsed
            't': profile.get_config().get('_auto_order_timeout', -1),

            #  Debug Auto fulfill timeout
            'd': 0
        }

        config['user'] = {
            'id': user.id,
            'username': user.username,
            'email': user.email
        }

        return JsonResponse(config)

    def post_user_config(self, request, user, data):
        if not user.can('edit_settings.sub'):
            raise PermissionDenied()

        profile = user.models_user.profile

        try:
            config = json.loads(profile.config)
        except:
            config = {}

        form_webapp = (data.get('from', False) == 'webapp')

        if data.get('single'):
            config[data.get('name')] = data.get('value')
            profile.config = json.dumps(config)
            profile.save()

            return self.api_success()

        bool_config = ['make_visisble', 'epacket_shipping', 'auto_ordered_mark']

        if form_webapp:
            bool_config += [
                'aliexpress_captcha',
                'validate_tracking_number',
                'aliexpress_as_notes',
                'aliexpress_as_order_tag',
                'aliexpress_as_custom_note',
                'order_custom_line_attr'
            ]

        for key in data:
            if key == 'from':
                continue

            if key in ['auto_margin', 'auto_compare_at']:
                if not data.get(key).endswith('%'):
                    config[key] = data[key] + '%'
                else:
                    config[key] = data[key]

            elif key in ['auto_margin_cents', 'auto_compare_at_cents']:
                try:
                    config[key] = data[key].replace('.', '')
                except:
                    config[key] = ''

            elif key in ['make_visisble', 'epacket_shipping']:
                config[key] = bool(data.get(key))
                bool_config.remove(key)

            elif key == 'shipping_method_filter':
                config[key] = True

                # Resets the store sync status the first time the filter is added to config
                for store in user.models_user.shopifystore_set.all():
                    try:
                        if shopify_orders_utils.is_store_synced(store):  # Only reset if store is already imported
                            ShopifySyncStatus.objects.filter(sync_type='orders', store=store) \
                                                     .update(sync_status=6)
                    except ShopifySyncStatus.DoesNotExist:
                        pass

            elif key == 'admitad_site_id':
                if data[key].startswith('http'):
                    config[key] = utils.remove_link_query(data[key]).strip('/ ').split('/').pop()
                elif not data[key]:
                    config[key] = ''
            else:
                if key != 'access_token':
                    config[key] = data[key]

        for key in bool_config:
            config[key] = (key in data)

        profile.config = json.dumps(config)
        profile.save()

        return self.api_success()

    def get_captcha_credits(self, request, user, data):
        if not user.can('aliexpress_captcha.use'):
            raise PermissionDenied()

        try:
            credits = user.models_user.captchacredit.remaining_credits
        except:
            credits = 0

        return self.api_success({
            'credits': credits,
            'user': user.models_user.username
        })

    def post_captcha_credits(self, request, user, data):
        if not user.can('aliexpress_captcha.use'):
            raise PermissionDenied()

        if user.models_user.captchacredit and user.models_user.captchacredit.remaining_credits > 0:
            user.models_user.captchacredit.remaining_credits -= 1
            user.models_user.captchacredit.save()
        else:
            return self.api_error('Insufficient Credits', status=402)

        return self.api_success({
            'remaining_credits': user.models_user.captchacredit.remaining_credits
        })

    def get_product_config(self, request, user, data):
        if not user.can('price_changes.use'):
            raise PermissionDenied()

        product = request.GET.get('product')
        if product:
            product = get_object_or_404(ShopifyProduct, id=product)
            permissions.user_can_view(request.user, product)
        else:
            return self.api_error('Product not found', status=404)

        try:
            config = json.loads(product.config)
        except:
            config = {}

        return JsonResponse(config)

    def post_product_config(self, request, user, data):
        if not user.can('price_changes.use'):
            raise PermissionDenied()

        product = data.get('product')
        if product:
            product = get_object_or_404(ShopifyProduct, id=product)
            permissions.user_can_edit(request.user, product)
        else:
            return self.api_error('Product not found', status=404)

        try:
            config = json.loads(product.config)
        except:
            config = {}

        for key in data:
            if key == 'product':
                continue
            config[key] = data[key]

        product.config = json.dumps(config)
        product.save()

        return self.api_success()

    def post_fulfill_order(self, request, user, data):
        try:
            store = ShopifyStore.objects.get(id=data.get('fulfill-store'))

            if not user.can('place_orders.sub', store):
                raise PermissionDenied()

            permissions.user_can_view(user, store)

        except ShopifyStore.DoesNotExist:
            return self.api_error('Store not found', status=404)

        fulfillment_data = {
            'store_id': store.id,
            'line_id': int(data.get('fulfill-line-id')),
            'order_id': data.get('fulfill-order-id'),
            'source_tracking': data.get('fulfill-traking-number'),
            'use_usps': data.get('fulfill-tarcking-link') == 'usps',
            'user_config': {
                'send_shipping_confirmation': data.get('fulfill-notify-customer'),
                'validate_tracking_number': False,
                'aftership_domain': user.get_config('aftership_domain', 'track')
            }
        }

        api_data = utils.order_track_fulfillment(**fulfillment_data)

        rep = requests.post(
            url=store.get_link('/admin/orders/{}/fulfillments.json'.format(data.get('fulfill-order-id')), api=True),
            json=api_data
        )

        try:
            rep.raise_for_status()

            return self.api_success()

        except:
            if 'is already fulfilled' not in rep.text and \
               'please try again' not in rep.text and \
               'Internal Server Error' not in rep.text:
                raven_client.captureException(
                    level='warning',
                    extra={'response': rep.text})

            try:
                errors = utils.format_shopify_error(rep.json())
                return self.api_error('Shopify Error: \n{}'.format(errors))
            except:
                return self.api_error('Shopify API Error')

    def get_order_data(self, request, user, data):
        version = request.META.get('HTTP_X_EXTENSION_VERSION')
        if version:
            required = None

            if version_compare(version, '1.25.6') < 0:
                required = '1.25.6'
            elif version_compare(version, '1.26.0') == 0:
                required = '1.26.1'

            if required:
                raven_client.captureMessage(
                    'Extension Update Required',
                    level='warning',
                    extra={'current': version, 'required': required})

                return self.api_error('Please Update The Extension To Version %s or Higher' % required, status=501)

        order_key = data.get('order')

        if not order_key.startswith('order_'):
            order_key = 'order_{}'.format(order_key)

        prefix, store, order, line = order_key.split('_')

        try:
            store = ShopifyStore.objects.get(id=store)
            permissions.user_can_view(user, store)
        except ShopifyStore.DoesNotExist:
            return self.api_error('Store not found', status=404)

        order = order_data_cache(order_key)
        if order:
            if not order['shipping_address'].get('address2'):
                order['shipping_address']['address2'] = ''

            order['ordered'] = False
            order['fast_checkout'] = user.get_config('_fast_checkout', True)
            order['solve'] = user.models_user.get_config('aliexpress_captcha', False)

            phone = order['order']['phone']
            if type(phone) is dict:
                phone_country, phone_number = order_phone_number(request, user.models_user, phone['number'], phone['country'])
                order['order']['phone'] = phone_number
                order['order']['phoneCountry'] = phone_country

            try:
                track = ShopifyOrderTrack.objects.get(
                    store=store,
                    order_id=order['order_id'],
                    line_id=order['line_id']
                )

                order['ordered'] = {
                    'time': arrow.get(track.created_at).humanize(),
                    'link': request.build_absolute_uri('/orders/track?hidden=2&query={}'.format(order['order_id']))
                }

            except ShopifyOrderTrack.DoesNotExist:
                pass
            except:
                raven_client.captureException()

            return JsonResponse(order, safe=False)
        else:
            return self.api_error('Not found: {}'.format(data.get('order')), status=404)

    def get_product_variant_image(self, request, user, data):
        try:
            store = ShopifyStore.objects.get(id=data.get('store'))
            permissions.user_can_view(user, store)
        except ShopifyStore.DoesNotExist:
            return self.api_error('Store not found', status=404)

        image = utils.get_shopify_variant_image(store, data.get('product'), data.get('variant'))

        if image and request.GET.get('thumb') == '1':
            image = shopify_image_thumb(image)

        if image and request.GET.get('redirect') == '1':
            return HttpResponseRedirect(image)
        elif image:
            return self.api_success({
                'image': image
            })
        else:
            return self.api_error('Image not found', status=404)

    def post_variants_mapping(self, request, user, data):
        product = ShopifyProduct.objects.get(id=data.get('product'))
        permissions.user_can_edit(user, product)

        supplier = product.productsupplier_set.get(id=data.get('supplier'))

        mapping = {}
        for k in data:
            if k != 'product' and k != 'supplier':
                mapping[k] = data[k]

        if not product.default_supplier:
            supplier = product.get_supplier_info()
            product.default_supplier = ProductSupplier.objects.create(
                store=product.store,
                product=product,
                product_url=product.get_original_info().get('url', ''),
                supplier_name=supplier.get('name'),
                supplier_url=supplier.get('url'),
                is_default=True
            )

            supplier = product.default_supplier

        product.set_variant_mapping(mapping, supplier=supplier)
        product.save()

        return self.api_success()

    def post_suppliers_mapping(self, request, user, data):
        product = ShopifyProduct.objects.get(id=data.get('product'))
        permissions.user_can_edit(user, product)

        suppliers_cache = {}

        mapping = {}
        shipping_map = {}

        with transaction.atomic():
            for k in data:
                if k.startswith('shipping_'):  # Save the shipping mapping for this supplier
                    shipping_map[k.replace('shipping_', '')] = json.loads(data[k])
                elif k.startswith('variant_'):  # Save the varinat mapping for supplier+variant
                    supplier_id, variant_id = k.replace('variant_', '').split('_')
                    supplier = suppliers_cache.get(supplier_id, product.productsupplier_set.get(id=supplier_id))

                    suppliers_cache[supplier_id] = supplier
                    var_mapping = {variant_id: data[k]}

                    product.set_variant_mapping(var_mapping, supplier=supplier, update=True)

                elif k == 'config':
                    product.set_mapping_config({'supplier': data[k]})

                elif k != 'product':  # Save the variant -> supplier mapping
                    mapping[k] = json.loads(data[k])

            product.set_suppliers_mapping(mapping)
            product.set_shipping_mapping(shipping_map)
            product.save()

        return self.api_success()

    def post_bundles_mapping(self, request, user, data):
        product = ShopifyProduct.objects.get(id=data.get('product'))
        permissions.user_can_edit(user, product)

        product.set_bundle_mapping(data.get('mapping'))
        product.save()

        return self.api_success()

    def get_order_fulfill(self, request, user, data):
        if int(data.get('count', 0)) >= 30:
            raise Http404('Not found')

        # Get Orders marked as Ordered

        orders = []

        order_ids = data.get('ids')
        unfulfilled_only = data.get('unfulfilled_only') != 'false' and not order_ids
        all_orders = data.get('all') == 'true' or order_ids

        shopify_orders = ShopifyOrderTrack.objects.filter(user=user.models_user, hidden=False) \
                                                  .defer('data') \
                                                  .order_by('updated_at')

        if unfulfilled_only:
            shopify_orders = shopify_orders.filter(source_tracking='') \
                                           .exclude(source_status='FINISH')

        if order_ids:
            shopify_orders = shopify_orders.filter(id__in=order_ids.split(','))

        if user.is_subuser:
            shopify_orders = shopify_orders.filter(store__in=user.profile.get_shopify_stores(flat=True))

        if data.get('store'):
            shopify_orders = shopify_orders.filter(store=data.get('store'))

        if not data.get('order_id') and not data.get('line_id') and not all_orders:
            limit_key = 'order_fulfill_limit_%d' % user.models_user.id
            limit = cache.get(limit_key)

            if limit is None:
                limit = orders_update_limit(orders_count=shopify_orders.count())

                if limit != 20:
                    cache.set(limit_key, limit, timeout=3600)

            if data.get('forced') == 'true':
                limit = limit * 2

            shopify_orders = shopify_orders[:limit]

        elif data.get('all') == 'true':
            shopify_orders = shopify_orders.order_by('created_at')

        if data.get('order_id') and data.get('line_id'):
            shopify_orders = shopify_orders.filter(order_id=data.get('order_id'), line_id=data.get('line_id'))

        if data.get('count_only') == 'true':
            return self.api_success({'pending': shopify_orders.count()})

        shopify_orders = serializers.serialize('python', shopify_orders,
                                               fields=('id', 'order_id', 'line_id',
                                                       'source_id', 'source_status',
                                                       'source_tracking', 'created_at'))

        for i in shopify_orders:
            fields = i['fields']
            fields['id'] = i['pk']

            if all_orders:
                fields['created_at'] = arrow.get(fields['created_at']).humanize()

            if fields['source_id'] and ',' in fields['source_id']:
                for j in fields['source_id'].split(','):
                    order_fields = copy.deepcopy(fields)
                    order_fields['source_id'] = j
                    order_fields['bundle'] = True
                    orders.append(order_fields)
            else:
                orders.append(fields)

        if not data.get('order_id') and not data.get('line_id'):
            ShopifyOrderTrack.objects.filter(user=user.models_user, id__in=[i['id'] for i in orders]) \
                                     .update(check_count=F('check_count') + 1, updated_at=timezone.now())

        return self.api_success(orders, safe=False)

    def post_order_place(self, request, user, data):
        try:
            store = ShopifyStore.objects.get(id=data.get('store'))
            permissions.user_can_view(user, store)

            if not user.can('place_orders.sub', store):
                raise PermissionDenied()

        except ShopifyStore.DoesNotExist:
            raven_client.captureException()
            return self.api_error('Store {} not found'.format(data.get('store')), status=404)

        order_id = data.get('order_id')
        line_id = data.get('line_id')

        shopify_order = utils.get_shopify_order(store, order_id)

        _order, customer_address = utils.shopify_customer_address(shopify_order)
        if customer_address['country_code'] != 'US':
            return self.api_error('Dropwow support US customers only')

        if not fulfill_shopify_order_line(store.id, shopify_order, customer_address, line_id=line_id):
            return self.api_error('Auto fulfill error')

        return self.api_success()

    def post_order_fulfill(self, request, user, data):
        try:
            store = ShopifyStore.objects.get(id=int(data.get('store')))
            if not user.can('place_orders.sub', store):
                raise PermissionDenied()
            permissions.user_can_view(user, store)
        except ShopifyStore.DoesNotExist:
            raven_client.captureException()
            return self.api_error('Store {} not found'.format(data.get('store')), status=404)

        # Mark Order as Ordered
        order_id = data.get('order_id')
        order_lines = data.get('line_id', '')
        order_line_sku = data.get('line_sku')
        source_id = data.get('aliexpress_order_id', '')

        try:
            assert len(source_id) > 0, 'Empty Order ID'
            source_id.encode('ascii')

            assert utils.safeInt(order_id), 'Order ID is not a numbers'
            # assert utils.safeInt(source_id), 'Aliexpress ID is not a numbers'
            # assert re.match('^[0-9]{10,}$', source_id) is not None, 'Not a valid Aliexpress Order ID: {}'.format(source_id)

            # source_id = int(source_id)

        except AssertionError as e:
            raven_client.captureMessage('Non valid Aliexpress Order ID')

            return self.api_error(e.message, status=501)

        except UnicodeEncodeError as e:
            return self.api_error('Order ID is not a valid', status=501)

        if not order_lines and order_line_sku:
            try:
                shopify_data = json.loads(data.get('shopify_data')) if data.get('shopify_data') else None
                line = utils.get_shopify_order_line(store, order_id, None, line_sku=order_line_sku, shopify_data=shopify_data)

            except requests.exceptions.HTTPError as e:
                if e.response.status_code in [401, 402, 403, 404, 429]:
                    return self.api_error('Shopify API Error', status=e.response.status_code)
                else:
                    raven_client.captureException(level='warning')
                    return self.api_error('Shopify API Error', status=500)

            if line:
                order_lines = str(line['id'])

        note_delay_key = 'store_{}_order_{}'.format(store.id, order_id)
        note_delay = cache.get(note_delay_key, 0)

        order_updater = utils.ShopifyOrderUpdater(store, order_id)

        if data.get('combined'):
            order_lines = order_lines.split(',')
            current_line = order_data_cache(store.id, order_id, order_lines[0])
            for key, order_data in order_data_cache(store.id, order_id, '*').items():
                if current_line and str(order_data['line_id']) not in order_lines \
                        and str(order_data['source_id']) == str(current_line['source_id']) \
                        and not ShopifyOrderTrack.objects.filter(store=store, order_id=order_id, line_id=order_data['line_id']).exists():
                    order_lines.append(str(order_data['line_id']))

            order_lines = ','.join(order_lines)

        for line_id in order_lines.split(','):
            if not line_id:
                return self.api_error('Order Line Was Not Found.', status=501)

            tracks = ShopifyOrderTrack.objects.filter(
                store=store,
                order_id=order_id,
                line_id=line_id
            )

            tracks_count = len(tracks)

            if tracks_count > 1:
                raven_client.captureMessage('More Than One Order Track', level='warning', extra={
                    'store': store.title,
                    'order_id': order_id,
                    'line_id': line_id,
                    'count': tracks.count()
                })

                tracks.delete()

            elif tracks_count == 1:
                saved_track = tracks.first()

                if order_line_sku and saved_track.shopify_status == 'fulfilled':
                    # Line is already fulfilled
                    return self.api_success()

                if saved_track.source_id and source_id != saved_track.source_id:
                    raven_client.captureMessage('Possible Double Order', level='warning', extra={
                        'store': store.title,
                        'order_id': order_id,
                        'line_id': line_id,
                        'old': {
                            'id': saved_track.source_id,
                            'date': arrow.get(saved_track.created_at).humanize(),
                        },
                        'new': source_id,
                    })

                    return self.api_error('This Order already have an Aliexpress Order ID', status=422)

            seem_source_orders = ShopifyOrderTrack.objects.filter(
                store=store,
                source_id=source_id
            ).values_list('order_id', flat=True)

            if len(seem_source_orders) and int(order_id) not in seem_source_orders and not data.get('forced'):
                raven_client.captureMessage('Linked to an other Order', level='warning', extra={
                    'store': store.title,
                    'order_id': order_id,
                    'line_id': line_id,
                    'source_id': source_id,
                    'seem_source_orders': list(seem_source_orders),
                })

                return self.api_error('Aliexpress Order ID is linked to an other Order', status=422)

            track, created = ShopifyOrderTrack.objects.update_or_create(
                store=store,
                order_id=order_id,
                line_id=line_id,
                defaults={
                    'user': user.models_user,
                    'source_id': source_id,
                    'created_at': timezone.now(),
                    'updated_at': timezone.now(),
                    'status_updated_at': timezone.now()
                }
            )

            try:
                order = ShopifyOrder.objects.get(store=store, order_id=order_id)
                need_fulfillment = order.need_fulfillment

                for line in order.shopifyorderline_set.all():
                    if line.line_id == utils.safeInt(line_id):
                        line.track = track
                        line.save()

                        need_fulfillment -= 1

                ShopifyOrder.objects.filter(id=order.id).update(need_fulfillment=need_fulfillment)

            except ShopifyOrder.DoesNotExist:
                pass

            profile = user.models_user.profile

            # TODO: Handle multi values in source_id
            if profile.get_config_value('aliexpress_as_notes', True):
                order_updater.mark_as_ordered_note(line_id, source_id)

            if profile.get_config_value('aliexpress_as_custom_note'):
                order_updater.mark_as_ordered_attribute(source_id)

            if profile.get_config_value('aliexpress_as_order_tag'):
                order_updater.mark_as_ordered_tag(source_id)

            store.pusher_trigger('order-source-id-add', {
                'track': track.id,
                'order_id': order_id,
                'line_id': line_id,
                'source_id': source_id,
            })

            cache.set(note_delay_key, note_delay + 5, timeout=5)

        aliexpress_order_tags = user.models_user.get_config('aliexpress_order_tags')
        if aliexpress_order_tags:
            order_updater.add_tag(aliexpress_order_tags)

        if not settings.DEBUG and 'oberlo.com' not in request.META.get('HTTP_REFERER', ''):
            order_updater.delay_save(countdown=note_delay)

        return self.api_success()

    def delete_order_fulfill(self, request, user, data):
        order_id = data.get('order_id')
        line_id = data.get('line_id')

        tracks = ShopifyOrderTrack.objects.filter(user=user.models_user, order_id=order_id, line_id=line_id)
        deleted_ids = []

        if len(tracks):
            for track in tracks:
                permissions.user_can_delete(user, track)

                for order in ShopifyOrder.objects.filter(store=track.store, shopifyorderline__track_id=track.id).distinct():
                    need_fulfillment = order.need_fulfillment
                    for line in order.shopifyorderline_set.all():
                        if line.track_id == track.id:
                            order.need_fulfillment += 1

                    ShopifyOrder.objects.filter(id=order.id).update(need_fulfillment=need_fulfillment)

                deleted_ids.append(track.id)
                track.delete()

                track.store.pusher_trigger('order-source-id-delete', {
                    'store_id': track.store.id,
                    'order_id': track.order_id,
                    'line_id': track.line_id,
                })

            return self.api_success()
        else:
            return self.api_error('Order not found.', status=404)

    def post_order_fulfill_update(self, request, user, data):
        if data.get('store'):
            store = ShopifyStore.objects.get(pk=int(data['store']))
            if not user.can('place_orders.sub', store):
                raise PermissionDenied()

        tracking_number = re.sub(r'[\n\r\t]', '', data.get('tracking_number')).strip()

        try:
            order = ShopifyOrderTrack.objects.get(id=data.get('order'))
            permissions.user_can_edit(user, order)

        except ShopifyOrderTrack.DoesNotExist:
            return self.api_error('Order Track Not Found', status=404)

        new_tracking_number = (tracking_number and tracking_number not in order.source_tracking)

        order.source_status = data.get('status')
        order.source_tracking = tracking_number
        order.status_updated_at = timezone.now()

        try:
            order_data = json.loads(order.data)
            if 'aliexpress' not in order_data:
                order_data['aliexpress'] = {}
        except:
            order_data = {'aliexpress': {}}

        order_data['aliexpress']['end_reason'] = data.get('end_reason')

        try:
            order_data['aliexpress']['order_details'] = json.loads(data.get('order_details'))
        except:
            pass

        if data.get('bundle'):
            if not order_data.get('bundle'):
                order_data['bundle'] = {}

            if not order_data['bundle'].get(data.get('source_id')):
                order_data['bundle'][data.get('source_id')] = {}

            order_data['bundle'][data.get('source_id')] = {
                'source_status': data.get('status'),
                'source_tracking': data.get('tracking_number'),
                'end_reason': data.get('end_reason'),
                'order_details': json.loads(data.get('order_details')),
            }

        order.data = json.dumps(order_data)

        order.save()

        tracking_number_tags = user.models_user.get_config('tracking_number_tags')
        if new_tracking_number and tracking_number_tags:
            order_updater = utils.ShopifyOrderUpdater(order.store, order.order_id)
            order_updater.add_tag(tracking_number_tags)
            order_updater.delay_save()

        return self.api_success()

    def post_order_info(self, request, user, data):

        aliexpress_ids = data.get('aliexpress_id')
        if aliexpress_ids:
            aliexpress_ids = aliexpress_ids if type(aliexpress_ids) is list else aliexpress_ids.split(',')
        else:
            try:
                aliexpress_ids = json.loads(request.body)['aliexpress_id']
                if type(aliexpress_ids) is not list:
                    aliexpress_ids = []
            except:
                pass

        if not len(aliexpress_ids):
            return self.api_error('Aliexpress ID not set', status=422)

        aliexpress_ids = [int(j) for j in aliexpress_ids]
        orders = {}

        for chunk_ids in [aliexpress_ids[x:x + 100] for x in xrange(0, len(aliexpress_ids), 100)]:
            # Proccess 100 max order at a time

            tracks = ShopifyOrderTrack.objects.filter(user=user.models_user) \
                                              .filter(source_id__in=chunk_ids) \
                                              .defer('data') \
                                              .order_by('store')

            if len(tracks):
                stores = {}
                # tracks = utils.get_tracking_orders(tracks[0].store, tracks)

                for track in tracks:
                    if track.store in stores:
                        stores[track.store].append(track)
                    else:
                        stores[track.store] = [track]

                tracks = []

                for store, store_tracks in stores.iteritems():
                    permissions.user_can_view(user, store)

                    for track in utils.get_tracking_orders(store, store_tracks):
                        tracks.append(track)

            for track in tracks:
                info = {
                    'aliexpress_id': track.source_id,
                    'shopify_order': track.order_id,
                    'tracking_number': track.source_tracking,
                    'shopify_url': track.store.get_link('/admin/orders/{}'.format(track.order_id)),
                }

                if track.order:
                    shopify_summary = [
                        u'Shopify Order: {}'.format(track.order['name']),
                        u'Shopify Total Price: <b>{}</b>'.format(money_format(track.order['total_price'], track.store)),
                        u'Ordered <b>{}</b>'.format(arrow.get(track.order['created_at']).humanize())
                    ]

                    for line in track.order['line_items']:
                        shopify_summary.append(u'<br><b>{}x {}</b> {} - {}'.format(
                            line['quantity'],
                            money_format(line['price'], track.store),
                            truncatewords(line['title'], 10),
                            truncatewords(line['variant_title'] or '', 5)
                        ).rstrip('- ').replace(' ...', '...'))

                    info.update({
                        'shopify_number': track.order['name'],
                        'shopify_status': track.order['fulfillment_status'],
                        'shopify_customer': utils.shopify_customer_address(track.order)[1],
                        'shopify_summary': "<br>".join(shopify_summary),
                    })

                if str(track.source_id) in orders:
                    orders[str(track.source_id)].append(info)
                else:
                    orders[str(track.source_id)] = [info]

        for i in [str(k) for k in aliexpress_ids]:
            if i not in orders:
                orders[i] = None

        return JsonResponse(orders, safe=False)

    def post_order_add_note(self, request, user, data):
        # Append to the Order note
        store = ShopifyStore.objects.get(id=data.get('store'))
        permissions.user_can_view(user, store)

        if utils.add_shopify_order_note(store, data.get('order_id'), data.get('note')):
            return self.api_success()
        else:
            return self.api_error('Shopify API Error', status=500)

    def post_order_note(self, request, user, data):
        # Change the Order note
        store = ShopifyStore.objects.get(id=data.get('store'))
        permissions.user_can_view(user, store)

        if utils.set_shopify_order_note(store, data.get('order_id'), data['note']):
            return self.api_success()
        else:
            return self.api_error('Shopify API Error', status=500)

    def post_order_fullfill_hide(self, request, user, data):
        order = ShopifyOrderTrack.objects.get(id=data.get('order'))
        permissions.user_can_edit(user, order)

        order.hidden = data.get('hide') == 'true'
        order.save()

        return self.api_success()

    def get_find_product(self, request, user, data):
        try:
            source_id = data.get('aliexpress')
            shopify_id = data.get('product')
            product = None

            if source_id:
                product = ShopifyProduct.objects.get(user=user.models_user, productsupplier__source_id=source_id)
            else:
                product = ShopifyProduct.objects.get(user=user.models_user, shopify_id=shopify_id)
            permissions.user_can_view(user, product)

            return self.api_success({
                'url': app_link(reverse('product_view', args=[product.id]))
            })
        except:
            return self.api_error('Product not found', status=404)

    def get_find_products(self, request, user, data):
        try:
            response = {}

            source_ids = data.get('aliexpress')
            source_ids = source_ids.split(',') if source_ids else None

            shopify_ids = data.get('product')
            shopify_ids = shopify_ids.split(',') if shopify_ids else []

            if source_ids:
                for i in source_ids:
                    response[str(i)] = None

                for supplier in ProductSupplier.objects.filter(product__user=user.models_user, source_id__in=source_ids):
                    response[str(supplier.source_id)] = app_link(reverse('product_view', args=[supplier.product_id]))

            elif shopify_ids:
                for i in shopify_ids:
                    response[str(i)] = None

                for product in ShopifyProduct.objects.filter(user=user.models_user, shopify_id__in=shopify_ids):
                    response[str(product.shopify_id)] = app_link(reverse('product_view', args=[product.id]))

            return self.api_success(response)
        except:
            return self.api_error('Product not found', status=404)

    def post_generate_reg_link(self, request, user, data):
        if not user.is_superuser and not user.has_perm('leadgalaxy.add_planregistration'):
            return self.api_error('Unauthorized API call', status=403)

        plan_id = int(data.get('plan'))
        if not user.is_superuser and plan_id != 8:
            return self.api_error('Unauthorized API call', status=403)

        plan = GroupPlan.objects.get(id=plan_id)
        reg = utils.generate_plan_registration(plan, {
            'email': data.get('email')
        })

        return self.api_success({
            'hash': reg.register_hash
        })

    def get_product_original_desc(self, request, user, data):
        try:
            product = ShopifyProduct.objects.get(id=data.get('product'))
            permissions.user_can_view(user, product)

            return HttpResponse(json.loads(product.get_original_data())['description'])
        except:
            return HttpResponse('')

    def get_timezones(self, request, user, data):
        return JsonResponse(utils.get_timezones(data.get('country')), safe=False)

    def get_countries(self, request, user, data):
        return JsonResponse(get_counrties_list(), safe=False)

    def post_user_profile(self, request, user, data):
        form = UserProfileForm(data)
        if form.is_valid():
            user.first_name = form.cleaned_data['first_name']
            user.last_name = form.cleaned_data['last_name']
            user.save()

            profile = user.profile
            profile.timezone = form.cleaned_data['timezone']
            profile.country = form.cleaned_data['country']

            if not profile.company:
                profile.company = UserCompany.objects.create()

            profile.company.name = form.cleaned_data['company_name']
            profile.company.address_line1 = form.cleaned_data['company_address_line1']
            profile.company.address_line2 = form.cleaned_data['company_address_line2']
            profile.company.city = form.cleaned_data['company_city']
            profile.company.state = form.cleaned_data['company_state']
            profile.company.zip_code = form.cleaned_data['company_zip_code']
            profile.company.country = form.cleaned_data['company_country']

            profile.company.save()
            profile.save()

            invoice_to_company = form.cleaned_data.get('invoice_to_company')
            if invoice_to_company is not None:
                profile.set_config_value('invoice_to_company', bool(invoice_to_company))

            request.session['django_timezone'] = form.cleaned_data['timezone']

            return self.api_success({'reload': True})

    def post_user_email(self, request, user, data):
        # TODO: Handle Payements and email changing
        form = UserProfileEmailForm(data=data, user=user)
        if form.is_valid():
            email = form.cleaned_data['email']
            password = form.cleaned_data['password2']

            email_change = (user.email != email)
            if email_change:
                user.email = email
                user.save()

                user.profile.add_email(email)

            if password:
                user.set_password(password)
                user.save()

                auth_user = authenticate(username=user.username, password=password)
                login(request, auth_user)

            return self.api_success({
                'email': email_change,
                'password': password
            })
        else:
            errors = []
            for key, val in form.errors.items():
                errors.append(u'{} Field error:\n   {}'.format(key.title(), ' - '.join([k for k in val])))

            return self.api_error('\n\n'.join(errors), status=422)

    def post_dropwow_integration(self, request, user, data):
        form = DropwowIntegrationForm(data=data, user=user)
        if form.is_valid():
            dropwow_account_email = form.cleaned_data['dropwow_account_email']
            dropwow_account_api_key = form.cleaned_data['dropwow_account_api_key']

            dropwow_account, created = DropwowAccount.objects.get_or_create(user=user)
            dropwow_account.email = dropwow_account_email
            dropwow_account.api_key = dropwow_account_api_key
            dropwow_account.save()

            return self.api_success()
        else:
            errors = []
            for key, val in form.errors.items():
                errors.append(u'{} Field error:\n   {}'.format(key.title(), ' - '.join([k for k in val])))

            return self.api_error('\n\n'.join(errors), status=422)

    def get_shipping_aliexpress(self, request, user, data):
        aliexpress_id = data.get('id')

        country_code = data.get('country', 'US')
        if country_code == 'GB':
            country_code = 'UK'

        data = utils.aliexpress_shipping_info(aliexpress_id, country_code)
        return JsonResponse(data, safe=False)

    def post_subuser_delete(self, request, user, data):
        try:
            subuser = User.objects.get(id=data.get('subuser'), profile__subuser_parent=user)
        except User.DoesNotExist:
            return self.api_error('User not found', status=404)
        except:
            return self.api_error('Unknown Error', status=500)

        profile = subuser.profile

        profile.subuser_parent = None
        profile.subuser_stores.clear()
        profile.plan = utils.get_plan(plan_hash='606bd8eb8cb148c28c4c022a43f0432d')
        profile.save()

        AccessToken.objects.filter(user=subuser).delete()

        return self.api_success()

    def post_subuser_invite(self, request, user, data):
        if not user.can('sub_users.use'):
            raise PermissionDenied('Sub User Invite')

        subuser_email = data.get('email', '').strip()

        if not EmailForm({'email': subuser_email}).is_valid():
            return self.api_error('Email is not valid', status=501)

        users = User.objects.filter(email__iexact=subuser_email)
        if users.count():
            if users.count() == 1:
                subuser = users.first()
                if subuser.profile.plan.is_free and not user.get_config('_limit_subusers_invite'):
                    plan = utils.get_plan(plan_slug='subuser-plan')
                    reg = utils.generate_plan_registration(plan=plan, sender=user, data={
                        'email': subuser_email,
                        'auto': True
                    })

                    subuser.profile.apply_registration(reg)

                    data = {
                        'sender': user,
                    }

                    send_email_from_template(
                        tpl='subuser_added.html',
                        subject='Invitation to join Dropified',
                        recipient=subuser_email,
                        data=data,
                    )

                    return self.api_success({
                        'hash': reg.register_hash
                    })

            return self.api_error('Email is is already registered to an account', status=501)

        if PlanRegistration.objects.filter(email__iexact=subuser_email).count():
            return self.api_error('An Invitation is already sent to this email', status=501)

        if user.get_config('_limit_subusers_invite'):
            raven_client.captureMessage('Sub User Invite Attempts', level='warning')
            return self.api_error('Server Error', status=501)

        plan = utils.get_plan(plan_slug='subuser-plan')
        reg = utils.generate_plan_registration(plan=plan, sender=user, data={
            'email': subuser_email
        })

        data = {
            'email': subuser_email,
            'sender': user,
            'reg_hash': reg.register_hash
        }

        send_email_from_template(
            tpl='subuser_invite.html',
            subject='Invitation to join Dropified',
            recipient=subuser_email,
            data=data,
        )

        return self.api_success({
            'hash': reg.register_hash
        })

    def delete_subuser_invite(self, request, user, data):
        if not user.can('sub_users.use'):
            raise PermissionDenied('Sub User Invite')

        PlanRegistration.objects.get(id=data.get('invite'), sender=user).delete()

        return self.api_success()

    def post_alert_archive(self, request, user, data):
        try:
            if data.get('all') == '1':
                store = ShopifyStore.objects.get(id=data.get('store'))
                permissions.user_can_view(user, store)

                AliexpressProductChange.objects.filter(product__store=store).update(hidden=1)

            else:
                alert = AliexpressProductChange.objects.get(id=data.get('alert'))
                permissions.user_can_edit(user, alert)

                alert.hidden = 1
                alert.save()

        except ShopifyStore.DoesNotExist:
            return self.api_error('Store not found', status=404)

        return self.api_success()

    def post_alert_delete(self, request, user, data):
        try:
            store = ShopifyStore.objects.get(id=data.get('store'))
            permissions.user_can_view(user, store)

            AliexpressProductChange.objects.filter(product__store=store).delete()

        except ShopifyStore.DoesNotExist:
            return self.api_error('Store not found', status=404)

        return self.api_success()

    def post_save_orders_filter(self, request, user, data):
        utils.set_orders_filter(user, data)
        return self.api_success()

    def post_import_product(self, request, user, data):
        try:
            store = ShopifyStore.objects.get(id=data.get('store'))
            permissions.user_can_view(user, store)
        except ShopifyStore.DoesNotExist:
            return self.api_error('Store not found', status=404)

        can_add, total_allowed, user_count = permissions.can_add_product(user.models_user, ignore_daily_limit=True)
        if not can_add:
            return self.api_error(
                'Your current plan allow up to %d saved products, currently you have %d saved products.'
                % (total_allowed, user_count), status=401)

        shopify_product = utils.safeInt(data.get('product'))
        supplier_url = data.get('supplier')
        product = None

        if shopify_product:
            found_products = user.models_user.shopifyproduct_set.filter(store=store, shopify_id=shopify_product)
            if len(found_products):
                if len(found_products) == 1 and not found_products[0].have_supplier():
                    product = found_products[0]
                else:
                    return self.api_error('Product is already imported/connected', status=422)
        else:
            return self.api_error('Shopify Product ID is missing', status=422)

        if not supplier_url:
            return self.api_error('Supplier URL is missing', status=422)

        if utils.get_domain(supplier_url) == 'myshopify':
            return self.api_error('Product supplier is not correct', status=422)

        if utils.get_domain(supplier_url) == 'aliexpress':
            if '/deep_link.htm' in supplier_url.lower():
                supplier_url = urlparse.parse_qs(urlparse.urlparse(supplier_url).query)['dl_target_url'].pop()

            if '//s.aliexpress.com' in supplier_url.lower():
                rep = requests.get(supplier_url, allow_redirects=False)
                rep.raise_for_status()

                supplier_url = rep.headers.get('location')

                if '/deep_link.htm' in supplier_url:
                    raven_client.captureMessage(
                        'Deep link in redirection',
                        level='warning',
                        extra={
                            'location': supplier_url,
                            'supplier_url': data.get('supplier')
                        })

        elif utils.get_domain(supplier_url) == 'alitems':
            supplier_url = urlparse.parse_qs(urlparse.urlparse(supplier_url).query)['ulp'].pop()

        else:
            raven_client.captureMessage('Unsupported Import Source', level='warning', extra={'url': supplier_url})

        supplier_url = utils.remove_link_query(supplier_url)

        if not product:
            product = ShopifyProduct(
                store=store,
                user=user.models_user,
                shopify_id=shopify_product,
                data=json.dumps({
                    'title': 'Importing...',
                    'variants': [],
                    'original_url': supplier_url
                })
            )

            permissions.user_can_add(user, product)
            product.set_original_data('{}')
            product.save()

        supplier = ProductSupplier.objects.create(
            store=product.store,
            product=product,
            product_url=supplier_url,
            supplier_name=data.get('vendor_name', 'Supplier'),
            supplier_url=data.get('vendor_url', 'http://www.aliexpress.com/'),
            is_default=True
        )

        product.set_default_supplier(supplier, commit=True)

        try:
            shopify_data = json.loads(data.get('shopify_data'))
        except:
            shopify_data = None

        tasks.update_shopify_product.delay(store.id, product.shopify_id, product_id=product.id, shopify_product=shopify_data)

        return self.api_success({'product': product.id})

    def get_description_templates(self, request, user, data):
        templates = DescriptionTemplate.objects.filter(user=user.models_user)
        if data.get('id'):
            templates = templates.filter(id=data.get('id'))

        templates_dict = [{
            'id': 0,
            'title': 'Default',
            'description': user.models_user.get_config('default_desc', '')
        }]

        for i in templates:
            templates_dict.append(model_to_dict(i, fields='id,title,description'))

        return self.api_success({
            'description_templates': templates_dict
        })

    def post_description_templates(self, request, user, data):
        """
        Add or edit description templates
        """

        if not data.get('title', '').strip():
            return self.api_error('Description Title is not set', status=422)

        if not data.get('description', '').strip():
            return self.api_error('Description is empty', status=422)

        if data.get('id'):
            template, created = DescriptionTemplate.objects.update_or_create(
                id=data.get('id'),
                user=user.models_user,
                defaults={
                    'title': data.get('title'),
                    'description': data.get('description')
                }
            )
        else:
            template = DescriptionTemplate.objects.create(
                user=user.models_user,
                title=data.get('title'),
                description=data.get('description')
            )

        template_dict = model_to_dict(template)

        return self.api_success({'template': template_dict}, status=200)

    def delete_description_templates(self, request, user, data):
        try:
            template = DescriptionTemplate.objects.get(id=data.get('id'))
            permissions.user_can_delete(user, template)

            template.delete()

        except ShopifyProduct.DoesNotExist:
            return self.api_error('Template not found', status=404)

        return self.api_success()

    def get_markup_rules(self, request, user, data):
        rules = PriceMarkupRule.objects.filter(user=user.models_user)
        if data.get('id'):
            rules = rules.filter(id=data.get('id'))

        rules_dict = []

        for i in rules:
            i_dict = model_to_dict(i, fields='id,name,min_price,max_price,markup_type,markup_value,markup_compare_value')
            i_dict['markup_type_display'] = i.get_markup_type_display()
            rules_dict.append(i_dict)

        return self.api_success({
            'markup_rules': rules_dict
        })

    def post_markup_rules(self, request, user, data):
        """
        Add or edit markup rules
        """

        min_price = 0
        if data.get('min_price', '').strip():
            min_price = utils.safeFloat(data.get('min_price', ''))

        max_price = -1
        if data.get('max_price', '').strip():
            max_price = utils.safeFloat(data.get('max_price', ''))

        if not data.get('markup_type', '').strip():
            return self.api_error('Markup Type is not set', status=422)

        if not data.get('markup_value', '').strip():
            return self.api_error('Markup Value is not set', status=422)
        markup_value = utils.safeFloat(data.get('markup_value', ''))

        if not data.get('markup_compare_value', '').strip():
            return self.api_error('Markup Value for Compare at price is not set', status=422)
        markup_compare_value = utils.safeFloat(data.get('markup_compare_value', ''))

        if data.get('id'):
            rule, created = PriceMarkupRule.objects.update_or_create(
                id=data.get('id'),
                user=user.models_user,
                defaults={
                    'name': data.get('name'),
                    'min_price': min_price,
                    'max_price': max_price,
                    'markup_type': data.get('markup_type'),
                    'markup_value': markup_value,
                    'markup_compare_value': markup_compare_value,
                }
            )
        else:
            PriceMarkupRule.objects.create(
                user=user.models_user,
                name=data.get('name'),
                min_price=min_price,
                max_price=max_price,
                markup_type=data.get('markup_type'),
                markup_value=markup_value,
                markup_compare_value=markup_compare_value,
            )

        return self.get_markup_rules(request, user, {})

    def delete_markup_rules(self, request, user, data):
        try:
            rule = PriceMarkupRule.objects.get(id=data.get('id'))
            permissions.user_can_delete(user, rule)

        except ShopifyProduct.DoesNotExist:
            return self.api_error('Markup not found', status=404)

        rule.delete()

        return self.get_markup_rules(request, user, {})

    def get_product_image_download(self, request, user, data):
        try:
            product = ShopifyProduct.objects.get(id=data.get('product'))
            permissions.user_can_view(user, product)

        except ShopifyProduct.DoesNotExist:
            return self.api_error('Product not found', status=404)

        images = json.loads(product.data).get('images')
        if not images:
            return self.api_error('Product doesn\'t have any images', status=422)

        tasks.create_image_zip.apply_async(args=[images, product.id], countdown=5)

        return self.api_success()
