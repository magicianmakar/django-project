import re
import traceback
from functools import cmp_to_key
from urllib.parse import parse_qs, urlparse
from urllib.request import urlopen

import arrow
import requests
import simplejson as json

from django.contrib.auth import authenticate, login
from django.contrib.auth.models import User
from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import PermissionDenied
from django.urls import reverse
from django.db.models import Q
from django.forms.models import model_to_dict
from django.http import HttpResponse, HttpResponseRedirect
from django.http import JsonResponse
from django.shortcuts import render, get_object_or_404
from django.template.defaultfilters import truncatewords
from django.utils import timezone

from raven.contrib.django.raven_compat.models import client as raven_client
from app.celery_base import celery_app

from stripe_subscription.stripe_api import stripe
from stripe_subscription.models import StripeSubscription, StripeCustomer
from stripe_subscription.utils import update_subscription

from shopified_core import permissions
from shopified_core.api_base import ApiBase
from shopified_core.encryption import save_aliexpress_password, delete_aliexpress_password
from shopified_core.shipping_helper import get_counrties_list
from shopified_core.utils import (
    safe_int,
    safe_float,
    app_link,
    get_domain,
    remove_link_query,
    send_email_from_template,
    order_data_cache,
    add_http_schema,
    base64_encode,
    CancelledOrderAlert
)

from shopify_orders import utils as shopify_orders_utils
from shopify_orders import tasks as shopify_orders_tasks
from shopify_orders.models import (
    ShopifyOrder,
    ShopifySyncStatus,
    ShopifyOrderVariant,
    ShopifyOrderLog,
)
from product_alerts.utils import unmonitor_store

from . import tasks
from . import utils
from .api_helper import ShopifyApiHelper
from .forms import (
    UserProfileEmailForm,
    UserProfileForm,
)
from .models import (
    AdminEvent,
    ClippingMagic,
    DescriptionTemplate,
    FeatureBundle,
    GroupPlan,
    PlanRegistration,
    PriceMarkupRule,
    ProductSupplier,
    ShopifyBoard,
    ShopifyOrderTrack,
    ShopifyProduct,
    ShopifyProductImage,
    ShopifyStore,
    UserCompany,
    UserProfile,
    UserUpload,
)

from .templatetags.template_helper import shopify_image_thumb, money_format
from stripe_subscription import utils as stripe_utils


class ShopifyStoreApi(ApiBase):
    store_label = 'Shopify'
    store_slug = 'shopify'
    board_model = ShopifyBoard
    product_model = ShopifyProduct
    order_track_model = ShopifyOrderTrack
    store_model = ShopifyStore
    helper = ShopifyApiHelper()

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

        unmonitor_store(store)

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
        for store, idx in list(data.items()):
            store = ShopifyStore.objects.get(id=store)
            permissions.user_can_edit(user, store)

            store.list_index = safe_int(idx, 0)
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
        # DEPRECATE: user pusher-based product save
        return self.post_shopify(request, user, data)

    def get_export_product(self, request, user, data):
        # DEPRECATE: user pusher-based product save
        task = tasks.export_product.AsyncResult(data.get('id'))
        count = safe_int(data.get('count'))

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
                    if isinstance(data, Exception) or isinstance(data, str):
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
            product_data['price'] = safe_float(data.get('price[%s]' % p))
            product_data['compare_at_price'] = safe_float(data.get('compare_at[%s]' % p))
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

    def post_product_remove_board(self, request, user, data):
        # DEPRECATED
        return self.delete_board_products(request, user, data)

    def post_board_delete(self, request, user, data):
        if not user.can('edit_product_boards.sub'):
            raise PermissionDenied()

        board = ShopifyBoard.objects.get(id=data.get('board'))
        permissions.user_can_delete(user, board)

        board.delete()

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

        product = safe_int(data.get('product'))
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
            ClippingMagic.objects.get(user=user.models_user)
        except ClippingMagic.DoesNotExist:
            ClippingMagic.objects.create(user=user.models_user, remaining_credits=5)

        if user.models_user.clippingmagic.remaining_credits <= 0:
            return self.api_error('Looks like your credits have run out', status=402)

        if action == 'edit':
            res = requests.post(
                api_url,
                files={
                    'image': urlopen(add_http_schema(data.get('image_url')))
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
                    user=user.models_user,
                    product=data.get('product_id'),
                    url=img_url[:510]
                )

                user.models_user.clippingmagic.remaining_credits -= 1
                user.models_user.clippingmagic.save()
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
                if error.get('message'):
                    response = 'ClippingMagic API Error:\n {}'.format(error['message'])
                else:
                    response = 'ClippingMagic API Error'

            raven_client.captureMessage('ClippingMagic API Error', level='warning', extra=res)

            return self.api_error(response, status=500)

    def post_youzign_images(self, request, user, data):
        api_url = 'https://www.youzign.com/api/designs/'

        auth_detils = {
            'key': user.models_user.get_config('yz_public_key'),
            'token': user.models_user.get_config('yz_access_token'),
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

        except Exception:
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

        plan = GroupPlan.objects.get(id=data.get('plan'))
        if not plan.is_free:
            return self.api_error('Plan should be changed from Stripe or from the user Profile page for Shopify', status=422)

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

        return self.api_success({
            'user': {
                'email': target_user.email
            },
            'bundle': {
                'title': bundle.title,
                'id': bundle.id
            }
        })

    def post_stripe_refund_charge(self, request, user, data):
        if not user.is_superuser and not user.is_staff:
            raise PermissionDenied()

        target_user = User.objects.get(id=data.get('user'))

        amount = safe_float(data.get('amount'))
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
        except stripe.error.InvalidRequestError as e:
            raven_client.captureException(level='warning')
            return self.api_error(str(e))

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

    def post_auto_fulfill_limit_reset(self, request, user, data):
        if not user.is_superuser and not user.is_staff:
            raise PermissionDenied()

        target_user = User.objects.get(id=data.get('user'))
        target_user.models_user.set_config('auto_fulfill_limit_start', arrow.utcnow().timestamp)

        AdminEvent.objects.create(
            user=user,
            target_user=target_user,
            event_type='refund_charge',
            data=json.dumps({'fulfill_limit_reset': arrow.utcnow().timestamp}))

        return self.api_success()

    def post_release_subuser(self, request, user, data):
        if not user.is_superuser and not user.is_staff:
            raise PermissionDenied()

        try:
            target_user = User.objects.get(id=data.get('user'))
        except User.DoesNotExist:
            return self.api_error('User not found', status=404)
        except:
            return self.api_error('Unknown Error', status=500)

        profile = target_user.profile

        if not profile.subuser_parent:
            return self.api_error('User is not a Sub User', status=422)

        profile.subuser_parent = None
        profile.subuser_stores.clear()
        profile.subuser_chq_stores.clear()

        if profile.plan.slug == 'subuser-plan':
            profile.apply_subscription(GroupPlan.objects.get(default_plan=1))

        profile.save()

        AdminEvent.objects.create(
            user=user,
            target_user=target_user,
            event_type='release_subuser',
            data='{}')

        return self.api_success()

    def post_apply_registration(self, request, user, data):
        if not user.is_superuser and not user.is_staff:
            raise PermissionDenied()

        target_user = User.objects.get(id=data.get('user'))
        reg = PlanRegistration.objects.get(id=data.get('id'))

        AdminEvent.objects.create(
            user=user,
            target_user=target_user,
            event_type='apply_registration',
            data=json.dumps({'register_id': reg.id, 'register_title': str(reg)}))

        if reg.get_usage_count() is not None:
            return self.api_error('Multi User Registration')

        target_user.profile.apply_registration(reg)

        return self.api_success()

    def delete_access_token(self, request, user, data):
        if not user.is_superuser:
            raise PermissionDenied()

        target_user = User.objects.get(id=data.get('user'))
        for i in target_user.accesstoken_set.all():
            i.delete()

        return self.api_success()

    def post_change_customer_id(self, request, user, data):
        if not user.is_superuser and not user.is_staff:
            raise PermissionDenied()

        target_user = User.objects.get(id=data.get('user'))

        if not data.get('convert'):
            if not target_user.is_stripe_customer():
                return self.api_error('User is not a Stripe Customer')
        else:
            if target_user.is_stripe_customer():
                return self.api_error('User is already a Stripe Customer')

            customer = stripe.Customer.retrieve(data.get('customer-id'))

            StripeCustomer.objects.create(
                customer_id=customer['id'],
                user=target_user,
                data=json.dumps(customer)
            )

            target_user.profile.shopify_app_store = False
            target_user.profile.set_config_value('shopify_app_store', False)
            target_user.profile.save()

        target_user.stripe_customer.customer_id = data.get('customer-id')
        target_user.stripe_customer.save()
        target_user.stripe_customer.refresh()

        subscribtions = []
        for i in stripe.Subscription.list(customer=data.get('customer-id')).data:
            subscribtions.append(i)

        if subscribtions:
            sub = subscribtions[0]
            sub_plan = stripe_utils.get_main_subscription_item_plan(sub)
            try:
                stripe_sub = StripeSubscription.objects.get(subscription_id=sub.id)
                stripe_sub.refresh(sub=sub)
            except StripeSubscription.DoesNotExist:
                plan = GroupPlan.objects.get(Q(id=sub.metadata.get('plan_id')) | Q(stripe_plan__stripe_id=sub_plan.id))

                if plan.is_stripe():
                    target_user.profile.change_plan(plan)

                update_subscription(target_user, plan, sub)
        else:
            target_user.profile.change_plan(utils.get_plan(
                payment_gateway='shopify',
                plan_slug='shopify-free-plan'))

        return self.api_success()

    def post_convert_to_strip(self, request, user, data):
        if not user.is_superuser and not user.is_staff:
            raise PermissionDenied()

        target_user = User.objects.get(id=data.get('user'))
        profile = target_user.profile

        profile.shopify_app_store = False
        profile.set_config_value('shopify_app_store', False)
        profile.save()

        return self.api_success()

    def post_reset_customer_balance(self, request, user, data):
        if not user.is_superuser and not user.is_staff:
            raise PermissionDenied()

        target_user = User.objects.get(id=data.get('user'))
        if not target_user.is_stripe_customer():
            return self.api_error('User is not a Stripe Customer')

        cus = stripe.Customer.retrieve(data.get('customer-id'))
        if not cus.account_balance:
            return self.api_error('User balance is already empty')

        cus.account_balance = 0
        cus.save()

        return self.api_success()

    def post_shopify_products(self, request, user, data):
        store = safe_int(data.get('store'))
        if not store:
            return self.api_error('No Store was selected', status=404)

        try:
            store = ShopifyStore.objects.get(id=store)
            permissions.user_can_view(user, store)

            page = safe_int(data.get('page'), 1)
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

                products = sorted(products, key=cmp_to_key(connected_cmp), reverse=True)

                if data.get('hide_connected'):
                    products = [p for p in products if not p.get('connected')]

            return JsonResponse({
                'products': products,
                'page': page,
                'next': page + 1 if (len(products) == limit or data.get('hide_connected')) else None,
            })

        except ShopifyStore.DoesNotExist:
            return self.api_error('Store not found', status=404)

    def post_product_metadata(self, request, user, data):
        if not user.can('product_metadata.use'):
            return self.api_error('Your current plan doesn\'t have this feature.', status=500)

        product = ShopifyProduct.objects.get(id=data.get('product'))
        permissions.user_can_edit(user, product)

        original_link = remove_link_query(data.get('original-link'))

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

        supplier_url = remove_link_query(data.get('supplier-link'))

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

        try:
            if user.models_user.get_config('update_product_vendor') and product.default_supplier and product.shopify_id:
                utils.update_shopify_product_vendor(store, product.shopify_id, product.default_supplier.supplier_name)
        except:
            raven_client.captureException()

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

        try:
            if user.models_user.get_config('supplier_change_inventory_sync', True) and product.is_connected:
                tasks.sync_shopify_product_quantities.apply_async(args=[product.id])

            if user.models_user.get_config('update_product_vendor') and product.default_supplier and product.shopify_id:
                utils.update_shopify_product_vendor(product.store, product.shopify_id, product.default_supplier.supplier_name)
        except:
            raven_client.captureException()

        return self.api_success()

    def post_sync_with_supplier(self, request, user, data):
        product = ShopifyProduct.objects.get(id=data.get('product'))
        permissions.user_can_edit(user, product)

        limit_key = 'product_inventory_sync_{}_{}'.format(product.id, product.default_supplier.id)

        if cache.get(limit_key):
            return self.api_error('Sync is in progress', status=422)

        if product.is_connected:
            tasks.sync_shopify_product_quantities.apply_async(args=[product.id], expires=600)
        else:
            return self.api_error('Product is not connected', status=422)

        cache.set(limit_key, True, timeout=500)

        return self.api_success()

    def post_add_user_upload(self, request, user, data):
        product = ShopifyProduct.objects.get(id=data.get('product'))
        permissions.user_can_edit(user, product)

        upload = UserUpload(user=user.models_user, product=product, url=data.get('url'))
        permissions.user_can_add(user, upload)

        upload.save()

        return self.api_success()

    def post_product_randomize_image_names(self, request, user, data):
        product = ShopifyProduct.objects.get(id=data.get('product'))
        permissions.user_can_edit(user, product)
        task = tasks.product_randomize_image_names.apply_async(args=[product.id], expires=120)
        return self.api_success({'id': str(task.id)})

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
        config['import'] = base64_encode(json.dumps(config['import']))

        for k in list(config.keys()):
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
            user.profile.get_shopify_stores().count() >= total_allowed

        config['extra_stores'] = extra_stores

        # Auto Order Timeout
        config['ot'] = {
            #  Start Auto fulfill after `t` is elapsed
            't': config.get('_auto_order_timeout', -1),

            #  Debug Auto fulfill timeout
            'd': cache.get('__ot__d') or config.get('__ot__d'),

            # Log page load time
            'pa': cache.get('__ot__pa') or config.get('__ot__pa'),
        }

        config['user'] = {
            'id': user.id,
            'username': user.username,
            'email': user.email
        }

        if data.get('stores'):
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

            config['stores'] = stores

        config['sync'] = {
            'new': not user.models_user.get_config('_disable_new_orders_sync', False)
        }

        if data.get('name'):
            named_config = {}
            for name in data.get('name').split(','):
                if name in config:
                    named_config[name] = config[name]

            config = named_config

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
                'aliexpress_edit_address',
                'validate_tracking_number',
                'aliexpress_as_notes',
                'aliexpress_as_order_tag',
                'aliexpress_as_custom_note',
                'order_custom_line_attr',
                'fix_aliexpress_address',
                'initial_inventory_sync',
                'supplier_change_inventory_sync',
                'update_product_vendor',
                'order_risk_levels_enabled',
                'send_alerts_to_subusers',
                'sync_delay_notify',
                'sync_delay_notify_email',
                'sync_delay_notify_push',
                'sync_delay_notify_highlight',
                'randomize_image_names',
                'price_update_for_increase',
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
                    config[key] = remove_link_query(data[key]).strip('/ ').split('/').pop()
                elif not data[key]:
                    config[key] = ''
            else:
                if key != 'access_token':
                    config[key] = data[key]

        for key in bool_config:
            config[key] = (key in data)

        if config.get('aliexpress_order_tags'):
            if re.findall('https?://', config.get('aliexpress_order_tags')):
                return self.api_error('Invalid Custom Tag - Order Placed', status=422)

        if config.get('tracking_number_tags'):
            if re.findall('https?://', config.get('tracking_number_tags')):
                return self.api_error('Invalid Custom Tag - Tracking Number Added', status=422)

        phone_number = config.get('order_phone_number')
        if phone_number and '2056577766' in re.sub('[^0-9]', '', phone_number) and user.models_user.username != 'chase':
            return self.api_error('The entered phone number is not allowed to be used. '
                                  'Please use a good contact number for you or your company.', status=422)

        profile.config = json.dumps(config)
        profile.save()

        return self.api_success()

    def get_user_boards(self, request, user, data):
        boards = []
        for i in user.get_boards():
            boards.append({
                'id': i.id,
                'title': i.title,
                'type': 'shopify',
                'favorite': i.favorite
            })

        for i in user.get_chq_boards():
            boards.append({
                'id': i.id,
                'title': i.title,
                'type': 'chq',
                'favorite': i.favorite
            })

        for i in user.get_woo_boards():
            boards.append({
                'id': i.id,
                'title': i.title,
                'type': 'woo',
                'favorite': i.favorite
            })

        for i in user.get_gear_boards():
            boards.append({
                'id': i.id,
                'title': i.title,
                'type': 'gear',
                'favorite': i.favorite
            })

        for i in user.get_gkart_boards():
            boards.append({
                'id': i.id,
                'title': i.title,
                'type': 'gkart',
                'favorite': i.favorite
            })

        return self.api_success({
            'boards': boards,
        })

    def get_captcha_credits(self, request, user, data):
        if not user.can('aliexpress_captcha.use'):
            raise PermissionDenied()

        try:
            credits = user.models_user.captchacredit.remaining_credits
        except:
            credits = 0

        if user.can('unlimited_catpcha.use'):
            credits = 1000

        return self.api_success({
            'credits': credits,
            'user': user.models_user.username
        })

    def post_captcha_credits(self, request, user, data):
        if not user.can('aliexpress_captcha.use'):
            raise PermissionDenied()

        remaining_credits = 0
        if not user.can('unlimited_catpcha.use'):
            if user.models_user.captchacredit and user.models_user.captchacredit.remaining_credits > 0:
                user.models_user.captchacredit.remaining_credits -= 1
                user.models_user.captchacredit.save()

                remaining_credits = user.models_user.captchacredit.remaining_credits
            else:
                return self.api_error('Insufficient Credits', status=402)
        else:
            remaining_credits = 1000

        return self.api_success({
            'remaining_credits': remaining_credits
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
            'location_id': data.get('fulfill-location-id', store.get_primary_location()),
            'user_config': {
                'send_shipping_confirmation': data.get('fulfill-notify-customer'),
                'validate_tracking_number': False,
                'aftership_domain': user.models_user.get_config('aftership_domain', 'track')
            }
        }

        api_data = utils.order_track_fulfillment(**fulfillment_data)

        rep = requests.post(
            url=store.get_link('/admin/orders/{}/fulfillments.json'.format(data.get('fulfill-order-id')), api=True),
            json=api_data
        )

        try:
            rep.raise_for_status()

            ShopifyOrderLog.objects.update_order_log(
                store=store,
                user=user,
                log='Manually Fulfilled in Shopify',
                order_id=fulfillment_data['order_id'],
                line_id=fulfillment_data['line_id']
            )

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

    def post_ignore_shopify_order_track_errors(self, request, user, data):
        try:
            track = ShopifyOrderTrack.objects.get(id=data.get('id'))
            track.errors = -1
            track.add_error('User {} Ignored this error'.format(user.email))
            track.save()
        except ShopifyOrderTrack.DoesNotExist:
            return self.api_error('Track not found', status=404)
        return self.api_success()

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

    def get_shopify_variants(self, request, user, data):
        try:
            product = ShopifyProduct.objects.get(id=data.get('product'))
            permissions.user_can_view(user, product)
        except ShopifyProduct.DoesNotExist:
            return self.api_error('Product not found', status=404)

        shopify_product = utils.get_shopify_product(product.store, product.shopify_id)

        images = {}
        for i in shopify_product['images']:
            for var in i['variant_ids']:
                images[var] = i['src']

        variants = []
        for i in shopify_product['variants']:
            variants.append({
                'id': i['id'],
                'title': i['title'],
                'image': shopify_image_thumb(images.get(i['id']))
            })

        return self.api_success({'variants': variants})

    def post_change_order_variant(self, request, user, data):
        try:
            store = ShopifyStore.objects.get(id=data.get('store'))
            permissions.user_can_view(user, store)
        except ShopifyStore.DoesNotExist:
            return self.api_error('Store not found', status=404)

        if not data.get('variant'):
            return self.api_error('Variant was not selected', status=422)

        order_updater = utils.ShopifyOrderUpdater(store, data.get('order'))

        if data.get('variant') == '-1':
            ShopifyOrderVariant.objects.filter(store=store, order_id=data.get('order'), line_id=data.get('line')) \
                                       .delete()

            order_updater.add_note('Variant reset to customer selection for line #{} by {}'.format(
                data.get('line'), user.first_name or user.username))
        else:
            ShopifyOrderVariant.objects.update_or_create(
                store=store,
                order_id=data.get('order'),
                line_id=data.get('line'),
                defaults={
                    'variant_id': data.get('variant'),
                    'variant_title': data.get('title'),
                }
            )

            order_updater.add_note("Variant changed to '{}' for line #{} by {}".format(
                data.get('title'), data.get('line'), user.first_name or user.username))

        if data.get('remember_variant') == 'true':
            product = ShopifyProduct.objects.get(id=data.get('product'), store=store)
            product.set_real_variant(data.get('current_variant'), data.get('variant'))

        order_updater.save_changes()

        return self.api_success()

    def post_bundles_mapping(self, request, user, data):
        product = ShopifyProduct.objects.get(id=data.get('product'))
        permissions.user_can_edit(user, product)

        product.set_bundle_mapping(data.get('mapping'))
        product.save()

        return self.api_success()

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

        result = shopify_orders_tasks.fulfill_shopify_order_line(store.id, shopify_order, customer_address, line_id=line_id)

        if type(result) is str:
            return self.api_error(result)

        elif not result:
            return self.api_error('No connected items that need placing in this order')

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
        source_type = data.get('source_type')
        from_oberlo = 'oberlo.com' in request.META.get('HTTP_REFERER', '')
        using_dropified_extension = request.META.get('HTTP_X_EXTENSION_VERSION')
        using_fulfillbox = request.META.get('HTTP_X_FULFILLBOX_VERSION')
        item_fulfillment_status = None

        try:
            assert len(source_id) > 0, 'Empty Order ID'
            source_id.encode('ascii')

            assert re.match('^https?://', source_id) is None, 'Supplier Order ID should not be a link'

        except AssertionError as e:
            if from_oberlo and (not source_id or not len(source_id)):
                # Handle a regression in the extension migration tool (1b59df9)
                return self.api_success({'message': 'Nothing to import (Aliexpress ID is empty)'}, status=202)
            else:
                raven_client.captureException(level='warning', tags={'oberlo': from_oberlo, 'shop': store.shop})

            return self.api_error(str(e), status=501)

        except UnicodeEncodeError:
            return self.api_error('Order ID is invalid', status=501)

        if not order_lines and order_line_sku:
            try:
                shopify_data = json.loads(data.get('shopify_data')) if data.get('shopify_data') else None
                line = utils.get_shopify_order_line(store, order_id, None, line_sku=order_line_sku, shopify_data=shopify_data)

                if line and from_oberlo:
                    item_fulfillment_status = line.get('fulfillment_status')

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
            for key, order_data in list(order_data_cache(store.id, order_id, '*').items()):
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
                tracks.delete()

            elif tracks_count == 1:
                saved_track = tracks.first()

                if order_line_sku and saved_track.shopify_status == 'fulfilled':
                    # Line is already fulfilled
                    return self.api_success()

                if saved_track.source_id and source_id != saved_track.source_id and not from_oberlo:
                    return self.api_error('This order already has a supplier order ID', status=422)

            seem_source_orders = ShopifyOrderTrack.objects.filter(
                store=store,
                source_id=source_id
            ).values_list('order_id', flat=True)

            if len(seem_source_orders) and int(order_id) not in seem_source_orders and not data.get('forced') and not from_oberlo:
                return self.api_error('Supplier order ID is linked to another order', status=409)

            while True:
                try:
                    track_defaults = {
                        'user': user.models_user,
                        'source_id': source_id,
                        'created_at': timezone.now(),
                        'updated_at': timezone.now(),
                        'status_updated_at': timezone.now()
                    }

                    if item_fulfillment_status is not None:
                        track_defaults['shopify_status'] = item_fulfillment_status

                    if source_type:
                        track_defaults['source_type'] = source_type

                    track, created = ShopifyOrderTrack.objects.update_or_create(
                        store=store,
                        order_id=order_id,
                        line_id=line_id,
                        defaults=track_defaults
                    )

                    if not from_oberlo:
                        if using_dropified_extension:
                            log = 'Order Placed In Aliexpress using Dropified Extension'
                        elif using_fulfillbox:
                            log = 'Order Placed In Aliexpress using Dropifed FulfilBox'
                        else:
                            log = 'Manually link to Aliexpress Order'

                        ShopifyOrderLog.objects.update_order_log(
                            store=store,
                            user=user,
                            log=log,
                            level='info',
                            icon='tag',
                            order_id=order_id,
                            line_id=line_id
                        )

                    break

                except ShopifyOrderTrack.MultipleObjectsReturned:
                    ShopifyOrderTrack.objects.filter(store=store, order_id=order_id, line_id=line_id).delete()
                    continue

            try:
                order = ShopifyOrder.objects.get(store=store, order_id=order_id)
                need_fulfillment = order.need_fulfillment

                for line in order.shopifyorderline_set.all():
                    if line.line_id == safe_int(line_id):
                        line.track = track
                        try:
                            line.save()
                        except:
                            pass

                        need_fulfillment -= 1

                ShopifyOrder.objects.filter(id=order.id).update(need_fulfillment=need_fulfillment)

            except ShopifyOrder.DoesNotExist:
                pass

            profile = user.models_user.profile

            # TODO: Handle multi values in source_id
            if profile.get_config_value('aliexpress_as_notes', True):
                order_updater.mark_as_ordered_note(line_id, source_id, track=track)

            if profile.get_config_value('aliexpress_as_custom_note'):
                order_updater.mark_as_ordered_attribute(source_id, track=track)

            if profile.get_config_value('aliexpress_as_order_tag'):
                order_updater.mark_as_ordered_tag(source_id)

            store.pusher_trigger('order-source-id-add', {
                'track': track.id,
                'order_id': order_id,
                'line_id': line_id,
                'source_id': source_id,
                'source_url': track.get_source_url(),
            })

            cache.set(note_delay_key, note_delay + 5, timeout=5)

        aliexpress_order_tags = user.models_user.get_config('aliexpress_order_tags')
        if aliexpress_order_tags:
            order_updater.add_tag(aliexpress_order_tags)

        if not settings.DEBUG and not from_oberlo:
            if order_updater.have_changes():
                order_updater.delay_save(countdown=note_delay)
            else:
                # Update the order if the user doesn't enable any note, attribues or tag change when an order if linked to Aliexpress
                # Otherwise we won't update the order in Shopify and no Webhook call will trigger Order Update for this order
                # TODO: Faster order fulfillement status update?
                tasks.update_shopify_order.apply_async(args=[store.id, order_id], kwargs={'from_webhook': False})

        if track.data and not from_oberlo:
            shopify_orders_tasks.check_track_errors.delay(track.id)

        return self.api_success({'order_track_id': track.id})

    def delete_order_fulfill(self, request, user, data):
        order_id = data.get('order_id')
        line_id = data.get('line_id')

        tracks = ShopifyOrderTrack.objects.filter(store__in=list(user.profile.get_shopify_stores(flat=True)), order_id=order_id, line_id=line_id)
        deleted_ids = []

        if len(tracks):
            for track in tracks:
                permissions.user_can_delete(user, track)

                for order in ShopifyOrder.objects.filter(store=track.store, shopifyorderline__track_id=track.id).distinct():
                    tasks.update_shopify_order.apply_async(args=[track.store.id, order.order_id], kwargs={'from_webhook': False})

                    need_fulfillment = order.need_fulfillment
                    for line in order.shopifyorderline_set.all():
                        if line.track_id == track.id:
                            order.need_fulfillment += 1

                    ShopifyOrder.objects.filter(id=order.id).update(need_fulfillment=need_fulfillment)

                deleted_ids.append(track.id)
                track.delete()

                ShopifyOrderLog.objects.update_order_log(
                    store=track.store,
                    user=user,
                    log='Delete Supplier Order ID (#{})'.format(track.source_id),
                    level='warning',
                    icon='times',
                    order_id=track.order_id,
                    line_id=track.line_id
                )

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

        models_user = user.models_user
        cancelled_order_alert = CancelledOrderAlert(models_user,
                                                    data.get('source_id'),
                                                    data.get('end_reason'),
                                                    order.source_status_details,
                                                    order)

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

        order_details = {}
        try:
            order_details = json.loads(data.get('order_details'))
            order_data['aliexpress']['order_details'] = order_details
        except:
            raven_client.captureException(level='warning')

        if data.get('bundle') and data['bundle'] != 'false':
            if not order_data.get('bundle'):
                order_data['bundle'] = {}

            if not order_data['bundle'].get(data.get('source_id')):
                order_data['bundle'][data.get('source_id')] = {}

            order_data['bundle'][data.get('source_id')] = {
                'source_status': data.get('status'),
                'source_tracking': data.get('tracking_number'),
                'end_reason': data.get('end_reason'),
                'order_details': order_details,
            }

        order.data = json.dumps(order_data)

        order.save()

        tracking_number_tags = models_user.get_config('tracking_number_tags')
        if new_tracking_number:
            if tracking_number_tags:
                order_updater = utils.ShopifyOrderUpdater(order.store, order.order_id)
                order_updater.add_tag(tracking_number_tags)
                order_updater.delay_save()

            ShopifyOrderLog.objects.update_order_log(
                store=order.store,
                user=user,
                log='Tracking Number Added',
                level='info',
                icon='truck',
                order_id=order.order_id,
                line_id=order.line_id
            )

        if order.data and order.errors != -1:
            shopify_orders_tasks.check_track_errors.delay(order.id)

        # Send e-mail notifications for cancelled orders
        cancelled_order_alert.send_email()

        return self.api_success()

    def post_order_info(self, request, user, data):

        aliexpress_ids = data.get('aliexpress_id')
        if aliexpress_ids:
            aliexpress_ids = aliexpress_ids if isinstance(aliexpress_ids, list) else aliexpress_ids.split(',')
        else:
            try:
                aliexpress_ids = json.loads(request.body)['aliexpress_id']
                if not isinstance(aliexpress_ids, list):
                    aliexpress_ids = []
            except:
                pass

        if not len(aliexpress_ids):
            return self.api_error('Aliexpress ID not set', status=422)

        fix_aliexpress_address = user.models_user.get_config('fix_aliexpress_address')
        german_umlauts = user.models_user.get_config('_use_german_umlauts')

        aliexpress_ids = [int(j) for j in aliexpress_ids]
        orders = {}

        for chunk_ids in [aliexpress_ids[x:x + 100] for x in range(0, len(aliexpress_ids), 100)]:
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

                for store, store_tracks in list(stores.items()):
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
                        'Shopify Order: {}'.format(track.order['name']),
                        'Shopify Total Price: <b>{}</b>'.format(money_format(track.order['total_price'], track.store)),
                        'Ordered <b>{}</b>'.format(arrow.get(track.order['created_at']).humanize())
                    ]

                    for line in track.order['line_items']:
                        shopify_summary.append('<br><b>{}x {}</b> {} - {}'.format(
                            line['quantity'],
                            money_format(line['price'], track.store),
                            truncatewords(line['title'], 10),
                            truncatewords(line['variant_title'] or '', 5)
                        ).rstrip('- ').replace(' ...', '...'))

                    info.update({
                        'shopify_number': track.order['name'],
                        'shopify_status': track.order['fulfillment_status'],
                        'shopify_customer': utils.shopify_customer_address(track.order, aliexpress_fix=fix_aliexpress_address,
                                                                           german_umlauts=german_umlauts)[1],
                        'shopify_summary': "<br>".join(shopify_summary),
                    })
                else:
                    info.update({
                        'shopify_number': 'ID: {}'.format(track.order_id),
                        'shopify_summary': 'Shopify information not availble'
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

    def get_find_product(self, request, user, data):
        try:
            source_id = data.get('aliexpress')
            shopify_id = data.get('product')
            product = None

            if source_id:
                supplier = ProductSupplier.objects.filter(product__user=user.models_user, source_id=source_id).first()
                if supplier:
                    product = supplier.product
            else:
                product = ShopifyProduct.objects.get(user=user.models_user, shopify_id=shopify_id)

            permissions.user_can_view(user, product)

            assert product.store.is_active

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
        if not user.is_superuser and not user.is_staff:
            return self.api_error('Unauthorized API call', status=403)

        plan_id = int(data.get('plan'))

        email = data.get('email', data.get('user')).strip()
        if not email:
            return self.api_error('Email address is empty', status=500)

        plan = GroupPlan.objects.get(id=plan_id)
        reg = utils.generate_plan_registration(plan, {'email': email})

        data = {
            'email': email,
            'reg_hash': reg.register_hash
        }

        send_email_from_template(
            tpl='registration_link_invite.html',
            subject='Welcome to Dropified!',
            recipient=email,
            data=data,
        )

        AdminEvent.objects.create(
            user=user,
            event_type='plan_invite',
            data=json.dumps({'plan': plan.title, 'email': email}))

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
            profile.company.vat = form.cleaned_data['vat']

            profile.company.save()
            profile.save()

            invoice_to_company = form.cleaned_data.get('invoice_to_company')
            if invoice_to_company is not None:
                profile.set_config_value('invoice_to_company', bool(invoice_to_company))

            use_relative_dates = form.cleaned_data.get('use_relative_dates')
            if use_relative_dates is not None:
                profile.set_config_value('use_relative_dates', bool(use_relative_dates))

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
            for key, val in list(form.errors.items()):
                errors.append('{} Field error:\n   {}'.format(key.title(), ' - '.join([k for k in val])))

            return self.api_error('\n\n'.join(errors), status=422)

    def post_youzign_integration(self, request, user, data):
        if not user.can('edit_settings.sub'):
            raise PermissionDenied()

        user.models_user.set_config('yz_public_key', data.get('yz_public_key') or '')
        user.models_user.set_config('yz_access_token', data.get('yz_access_token') or '')

        return self.api_success()

    def post_aliexpress_integration(self, request, user, data):
        if not user.can('edit_settings.sub'):
            raise PermissionDenied()

        if data.get('ali_pass') == 'password is set':
            return self.api_error('Please Enter your Aliexpress account password')

        current_email = user.models_user.get_config('ali_email')
        if current_email:
            # Delete any saved email/password in case the user change his email, we won't have "stale" files
            delete_aliexpress_password(user, current_email)

        save_aliexpress_password(user, data.get('ali_email'), data.get('ali_pass'))

        # Save Aliexpress email in the user config, maybe we should use a better method (ex: each store with unique Aliexpress account)
        user.models_user.set_config('ali_email', data.get('ali_email') or '')

        return self.api_success()

    def get_shipping_aliexpress(self, request, user, data):
        aliexpress_id = data.get('id')

        country_code = data.get('country', 'US')
        if country_code == 'GB':
            country_code = 'UK'

        data = utils.aliexpress_shipping_info(aliexpress_id, country_code)
        return JsonResponse(data, safe=False)

    def post_save_orders_filter(self, request, user, data):
        utils.set_orders_filter(user, data)
        return self.api_success()

    def post_save_shopify_products_filter(self, request, user, data):
        utils.set_shopify_products_filter(user, data)
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

        shopify_product = safe_int(data.get('product'))
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

        if get_domain(supplier_url) == 'myshopify':
            return self.api_error('Product supplier is not correct', status=422)

        if get_domain(supplier_url) == 'aliexpress':
            if '/deep_link.htm' in supplier_url.lower():
                supplier_url = parse_qs(urlparse(supplier_url).query)['dl_target_url'].pop()

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

        elif get_domain(supplier_url) == 'alitems':
            supplier_url = parse_qs(urlparse(supplier_url).query)['ulp'].pop()

        else:
            if 'app.oberlo.com/suppliers' not in supplier_url:
                raven_client.captureMessage('Unsupported Import Source', level='warning', extra={'url': supplier_url})

        supplier_url = remove_link_query(supplier_url)

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
            supplier_url=remove_link_query(data.get('vendor_url', 'http://www.aliexpress.com/')),
            is_default=True
        )

        product.set_default_supplier(supplier, commit=True)

        try:
            shopify_data = json.loads(data.get('shopify_data'))
        except:
            shopify_data = None

        if data.get('from') == 'orders':
            tasks.update_product_connection.delay(store.id, shopify_product)

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
            min_price = safe_float(data.get('min_price', ''))

        max_price = -1
        if data.get('max_price', '').strip():
            max_price = safe_float(data.get('max_price', ''))

        if not data.get('markup_type', '').strip():
            return self.api_error('Markup Type is not set', status=422)

        if not data.get('markup_value', '').strip():
            return self.api_error('Markup Value is not set', status=422)
        markup_value = safe_float(data.get('markup_value', ''))

        if not data.get('markup_compare_value', '').strip():
            return self.api_error('Markup Value for Compare at price is not set', status=422)
        markup_compare_value = safe_float(data.get('markup_compare_value', ''))

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

    def post_calculate_sales(self, request, user, data):
        if not user.is_superuser:
            raise PermissionDenied()

        task = tasks.calculate_sales.apply_async(args=[user.id, data['period']])

        return self.api_success({'task': task.id})

    def get_user_statistics(self, request, user, data):
        stores = cache.get('user_statistics_{}'.format(user.id))

        if not stores and not data.get('cache_only'):
            if user.models_user.profile.get_shopify_stores().count() < 10:
                task = tasks.calculate_user_statistics.apply_async(args=[user.id], expires=60)
                return self.api_success({'task': task.id})

        return self.api_success({'stores': stores})

    def post_order_risks(self, request, user, data):
        store = ShopifyStore.objects.get(id=data.get('store'))
        permissions.user_can_view(user, store)

        task = tasks.shopify_orders_risk.apply_async(args=[store.id, data.get('orders')], expires=120)

        return self.api_success({'task': task.id})

    def get_search_shopify_products(self, request, user, data):
        try:
            store = ShopifyStore.objects.get(id=data.get('store'))
            permissions.user_can_view(user, store)
        except ShopifyStore.DoesNotExist:
            return self.api_error('Store not found', status=404)

        title = data.get('title')
        category = data.get('category')
        status = data.get('status')
        ppp = data.get('ppp')
        page = data.get('current_page')

        # fetch all shopify products asynchronously
        task = tasks.search_shopify_products.apply_async(
            args=[store.id, title, category, status, ppp, page],
            queue='priority_high',
            expires=60)

        return self.api_success({'task': task.id})

    def get_search_shopify_products_cached(self, request, user, data):
        cache_key = 'shopify_products_%s' % data.get('task')
        products = cache.get(cache_key)
        cache.delete(cache_key)
        return self.api_success({
            'products': products
        })

    def post_export_tracked_orders(self, request, user, data):
        if user.is_subuser:
            return self.api_error('Sub Users are not allowed to Export Orders', status=403)

        params = {
            'date': data.get('date'),
            'query': data.get('query'),
            'tracking': data.get('tracking'),
            'fulfillment': data.get('fulfillment'),
            'reason': data.get('reason'),
            'hidden': data.get('hidden'),
            'store_id': data.get('store'),
            'user_id': user.id,
        }

        cache_key = 'track_export_{}_{}'.format(user.id, data['store'])

        cache.set(cache_key, True, timeout=600)

        tasks.generate_tracked_order_export.apply_async(args=[params], expires=180)

        return self.api_success({
            'email': user.email
        })

    def post_products_supplier_sync(self, request, user, data):
        try:
            store = ShopifyStore.objects.get(id=data.get('store'))
            permissions.user_can_edit(user, store)
        except ShopifyStore.DoesNotExist:
            return self.api_error('Store not found', status=404)

        user_store_supplier_sync_key = 'user_store_supplier_sync_{}_{}'.format(user.id, store.id)
        if cache.get(user_store_supplier_sync_key) is not None:
            return self.api_error('Sync in progress', status=404)

        sync_price = data.get('sync_price', False)
        price_markup = safe_float(data['price_markup'])
        compare_markup = safe_float(data['compare_markup'])
        sync_inventory = data.get('sync_inventory', False)

        task = tasks.products_supplier_sync.apply_async(
            args=[store.id, sync_price, price_markup, compare_markup, sync_inventory, user_store_supplier_sync_key], expires=180)
        cache.set(user_store_supplier_sync_key, task.id, timeout=3600 * 60)
        return self.api_success({'task': task.id})

    def post_products_supplier_sync_stop(self, request, user, data):
        try:
            store = ShopifyStore.objects.get(id=data.get('store'))
            permissions.user_can_edit(user, store)
        except ShopifyStore.DoesNotExist:
            return self.api_error('Store not found', status=404)

        user_store_supplier_sync_key = 'user_store_supplier_sync_{}_{}'.format(user.id, store.id)
        task_id = cache.get(user_store_supplier_sync_key)
        if task_id is not None:
            celery_app.control.revoke(task_id, terminate=True)
            cache.delete(user_store_supplier_sync_key)
            return self.api_success()
        return self.api_error('No Sync in progress', status=404)

    def post_auto_order_status(self, request, user, data):
        try:
            store = ShopifyStore.objects.get(id=data.get('store'))
            permissions.user_can_view(user, store)
        except ShopifyStore.DoesNotExist:
            return self.api_error('Store not found', status=404)

        store.pusher_trigger('order-status-update', {
            'orders': data['orders']
        })

        return self.api_success()

    def get_shopify_locations(self, request, user, data):
        try:
            store = ShopifyStore.objects.get(id=data.get('store'))
            permissions.user_can_view(user, store)

        except ShopifyStore.DoesNotExist:
            return self.api_error('Store not found', status=404)

        locations_url = store.get_link('/admin/locations.json', api=True)
        response = requests.get(locations_url)
        locations = response.json()

        return self.api_success(locations)

    def post_shopify_location(self, request, user, data):
        try:
            store = ShopifyStore.objects.get(id=request.POST.get('store'))
            permissions.user_can_view(user, store)

        except ShopifyStore.DoesNotExist:
            return self.api_error('Store not found', status=404)

        store.primary_location = safe_int(request.POST.get('primary_location'), None)
        store.save()

        return self.api_success()

    def get_track_log(self, request, user, data):
        try:
            store = ShopifyStore.objects.get(id=data.get('store'))
            permissions.user_can_view(user, store)

            track_log = ShopifyOrderLog.objects.get(store=store, order_id=data['order_id'])

        except ShopifyStore.DoesNotExist:
            return self.api_error('Store not found', status=404)

        except ShopifyOrderLog.DoesNotExist:
            return self.api_error('No log found', status=404)

        except ShopifyOrderLog.DoesNotExist:
            return self.api_error('Order not found', status=404)

        except ShopifyOrderLog.MultipleObjectsReturned:
            logs = []
            track_log = None

            # Merge duplicate logs
            for track in ShopifyOrderLog.objects.filter(store=store, order_id=data['order_id']):
                for i in track.get_logs(sort=False):
                    logs.append(i)

                if track_log is None:
                    track_log = track

                track_log.logs = json.dumps(logs)
                track_log.save()

            # Delete duplicate entries
            ShopifyOrderLog.objects.filter(store=store, order_id=data['order_id']).exclude(id=track_log.id).delete()

        order_data = utils.get_shopify_order(store, data['order_id'])

        logs = track_log.get_logs(pretty=True, include_webhooks=True, order_data=order_data)

        if track_log.seen:
            track_log.seen = 0
            track_log.save()

        store.pusher_trigger('track-log-update', {
            'order_id': track_log.order_id,
            'seen': track_log.seen,
        })

        return render(request, 'partial/tracking_details_modal_content.html', {
            'order_id': data['order_id'],
            'store': store,
            'logs': logs,
            'request': request,
        })

    def post_track_log(self, request, user, data):
        try:
            store = ShopifyStore.objects.get(id=data.get('store'))
            permissions.user_can_view(user, store)

        except ShopifyStore.DoesNotExist:
            return self.api_error('Store not found', status=404)

        log = ShopifyOrderLog.objects.update_order_log(
            store=store,
            user=user if 'user' not in data else int(data['user']),
            log=data['log'],
            order_id=data.get('order_id'),
            level=data.get('level'),
            icon=data.get('icon'),
            line_id=data.get('line_id')
        )

        store.pusher_trigger('track-log-update', {
            'order_id': log.order_id,
            'seen': log.seen,
        })

        return self.api_success({
            'log': log.get_logs()
        })
