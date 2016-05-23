# -*- coding: utf-8 -*-
from django.shortcuts import render, get_object_or_404, render_to_response
from django.http import HttpResponse, HttpResponseRedirect, Http404
from django.contrib.auth.decorators import login_required
from django.contrib.auth import logout as user_logout
from django.shortcuts import redirect
from django.template import Context, Template, RequestContext
from django.contrib.auth.models import User
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db.models import Count, F, Q
from django.contrib.auth import authenticate, login
from django.http import JsonResponse
from django.core.urlresolvers import reverse
from django.core.mail import send_mail
from django.utils import timezone
from django.core.cache import cache

from unidecode import unidecode

from app import settings

from .models import *
from .forms import *
import tasks

import os
import re
import simplejson as json
import time
import requests
import arrow
import traceback
from raven.contrib.django.raven_compat.models import client as raven_client

import utils
from shopify_orders import utils as shopify_orders_utils
from shopify_orders.models import ShopifyOrder

from province_helper import load_uk_provincess


@login_required
def index_view(request):
    stores = request.user.profile.get_active_stores()
    config = request.user.models_user.profile.get_config()

    first_visit = config.get('_first_visit', True)
    intro_video = config.get('_intro_video', True)

    if first_visit:
        request.user.set_config('_first_visit', False)

    if intro_video:
        request.user.set_config('_intro_video', False)

    if request.user.profile.plan.slug == 'jvzoo-free-gift':
        first_visit = False
        intro_video = True

    return render(request, 'index.html', {
        'stores': stores,
        'config': config,
        'first_visit': first_visit or request.GET.get('new'),
        'intro_video': intro_video or request.GET.get('intro'),
        'page': 'index',
        'breadcrumbs': ['Stores']
    })


def api(request, target):
    method = request.method
    if method == 'POST':
        data = request.POST
    elif method == 'GET' or method == 'DELETE':
        data = request.GET
    else:
        raven_client.captureMessage('Unsupported Request Method', extra={'method': method})
        return JsonResponse({'error': 'Unsupported Request Method'}, status=501)

    if 'access_token' in data:
        token = data.get('access_token')
        user = utils.get_user_from_token(token)
    else:
        if request.user.is_authenticated():
            user = request.user
        else:
            user = None

    if target not in ['login', 'shopify', 'shopify-update', 'save-for-later', 'shipping-aliexpress'] and not user:
        return JsonResponse({'error': 'Unauthenticated API call.'}, status=401)

    if user:
        raven_client.user_context({
            'id': user.id,
            'username': user.username,
            'email': user.email
        })
    else:
        raven_client.user_context({
            'id': 0,
            'username': 'Anonymous',
        })

    raven_client.context.merge(raven_client.get_data_from_request(request))

    try:
        res = proccess_api(request, user, method, target, data)
        if res is None:
            raven_client.captureMessage('API Response is empty')
            res = JsonResponse({'error': 'Internal Server Error'}, status=500)

    except PermissionDenied as e:
        raven_client.captureException()
        res = JsonResponse({'error': 'Permission Denied: %s' % e.message}, status=403)

    except requests.Timeout:
        raven_client.captureException()
        res = JsonResponse({'error': 'API Request Timeout'}, status=501)

    except:
        raven_client.captureException()
        res = JsonResponse({'error': 'Internal Server Error'}, status=500)

    raven_client.context.clear()

    return res


def proccess_api(request, user, method, target, data):
    if target == 'login':
        username = data.get('username')
        password = data.get('password')

        if not username or not password:
            return JsonResponse({'error': 'Username or password not set'}, status=403)

        if utils.login_attempts_exceeded(username):
            raven_client.context.merge(raven_client.get_data_from_request(request))
            raven_client.captureMessage('Maximum login attempts reached',
                                        extra={'username': username, 'from': 'API'},
                                        level='warning')

            return JsonResponse({'error': 'You have reached the maximum login attempts.\n'
                                          'Please try again later.'}, status=403)

        if '@' in username:
            try:
                username = User.objects.get(email__iexact=username).username
            except:
                return JsonResponse({'error': 'Unvalide email or password'})

        user = authenticate(username=username, password=password)
        if user is not None:
            if user.is_active:
                token = utils.get_access_token(user)

                return JsonResponse({
                    'token': token,
                    'user': {
                        'username': user.username,
                        'email': user.email
                    }
                }, safe=False)

        return JsonResponse({'error': 'Unvalide username or password'})

    if method == 'POST' and target == 'register':
        return JsonResponse({'error': 'Please Visit Shopified App Website to register a new account:\n\n'
                                      'http://app.shopifiedapp.com/accounts/register\n.'}, status=501)

    if method == 'GET' and target == 'stores':
        stores = []
        for i in user.profile.get_active_stores():
            stores.append({
                'id': i.id,
                'name': i.title,
                'url': i.get_api_url(hide_keys=True)
            })

        return JsonResponse(stores, safe=False)

    if method == 'POST' and target == 'add-store':
        name = data.get('name')
        url = data.get('url')

        can_add, total_allowed, user_count = user.profile.can_add_store()

        if not can_add:
            return JsonResponse({
                'error': 'Your current plan allow up to %d linked stores, currently you have %d linked stores.'
                         % (total_allowed, user_count)
            })

        if user.is_subuser:
            return JsonResponse({'error': 'Sub-Users can not add new stores.'})

        store = ShopifyStore(title=name, api_url=url, user=user.models_user)
        user.can_add(store)

        try:
            info = store.get_info
            if not store.title:
                store.title = info['name']
        except:
            return JsonResponse({'error': 'Shopify Store link is not correct.'}, status=500)

        store.save()

        utils.attach_webhooks(store)

        stores = []
        for i in user.profile.get_active_stores():
            stores.append({
                'id': i.id,
                'name': i.title,
                'url': i.get_api_url(hide_keys=True)
            })

        return JsonResponse(stores, safe=False)

    if method == 'POST' and target == 'delete-store':
        store_id = data.get('store')
        move_to = data.get('move-to')

        store = ShopifyStore.objects.get(id=store_id)
        user.can_delete(store)

        # Sub users can't reach here
        move_to_store = ShopifyStore.objects.get(id=move_to, user=user)
        ShopifyStore.objects.filter(id=store_id, user=user).update(is_active=False)

        target_store = ShopifyStore.objects.get(id=store_id, user=user)
        target_store.is_active = False
        target_store.save()

        target_store.shopifyproduct_set.update(store=move_to_store)
        target_store.shopifyproductexport_set.update(store=move_to_store)
        target_store.shopifyproductimage_set.update(store=move_to_store)

        utils.detach_webhooks(target_store)

        stores = []
        for i in user.profile.get_active_stores():
            stores.append({
                'id': i.id,
                'name': i.title,
                'url': i.get_api_url(hide_keys=True)
            })

        return JsonResponse(stores, safe=False)

    if method == 'POST' and target == 'update-store':
        store = ShopifyStore.objects.get(id=data.get('store'))
        user.can_edit(store)

        store_title = data.get('title')
        store_api_url = data.get('url')
        api_url_changes = (store.api_url != data.get('url'))

        store_check = ShopifyStore(title=store_title, api_url=store_api_url, user=user)  # Can't be a sub user
        try:
            info = store_check.get_info
            if not store_title:
                store_title = info['name']
        except:
            return JsonResponse({'error': 'Shopify Store link is not correct.'}, status=500)

        if api_url_changes:
            utils.detach_webhooks(store)

        store.title = store_title
        store.api_url = store_api_url
        store.save()

        if api_url_changes:
            utils.attach_webhooks(store)

        return JsonResponse({'status': 'ok'})

    if method == 'GET' and target == 'store-verify':
        try:
            store = ShopifyStore.objects.get(id=data.get('store'))
            user.can_view(store)

        except ShopifyStore.DoesNotExist:
            return JsonResponse({'error': 'Store not found'}, status=404)

        try:
            info = store.get_info
            return JsonResponse({'status': 'ok', 'store': info['name']})

        except:
            return JsonResponse({'error': 'Shopify Store link is not correct.'}, status=500)

    if method == 'GET' and target == 'product':
        try:
            product = ShopifyProduct.objects.get(id=data.get('product'))
            user.can_view(product)

        except ShopifyProduct.DoesNotExist:
            return JsonResponse({'error': 'Product not found'})

        return JsonResponse(json.loads(product.data), safe=False)

    if method == 'GET' and target == 'products-info':
        products = {}
        for p in data.getlist('products[]'):
            try:
                product = ShopifyProduct.objects.get(id=p)
                user.can_view(product)

                products[p] = json.loads(product.data)
            except:
                return JsonResponse({'error': 'Product not found'})

        return JsonResponse(products, safe=False)

    if method == 'POST' and (target == 'shopify' or target == 'shopify-update' or target == 'save-for-later'):
        req_data = json.loads(request.body)
        delayed = req_data.get('b')

        if 'access_token' in req_data:
            token = req_data['access_token']
            user = utils.get_user_from_token(token)

            if not user:
                return JsonResponse({'error': 'Unvalide access token: %s' % (token)}, status=401)
        else:
            if request.user.is_authenticated():
                user = request.user
            else:
                return JsonResponse({'error': 'Unauthenticated user'}, status=401)

        if not delayed or target == 'save-for-later':
            result = tasks.export_product(req_data, target, user.id)
            result = utils.fix_product_url(result, request)

            return JsonResponse(result, safe=False)
        else:
            task = tasks.export_product.delay(req_data, target, user.id)

            return JsonResponse({
                'status': 'ok',
                'id': str(task.id)
            })

    if method == 'GET' and target == 'export-product':
        task = tasks.export_product.AsyncResult(data.get('id'))
        count = utils.safeInt(data.get('count'))

        if count == 60:
            raven_client.context.merge(raven_client.get_data_from_request(request))
            raven_client.captureMessage('Celery Task is taking too long.', level='warning')
        if count > 120:
            raven_client.captureMessage('Terminate Celery Task.',
                                        extra={'task': data.get('id')},
                                        level='warning')

            task.revoke(terminate=True)
            return JsonResponse({'error': 'Export Error'}, status=500)

        if not task.ready():
            return JsonResponse({
                'status': 'ok',
                'ready': False
            })
        else:
            data = task.result
            data = utils.fix_product_url(data, request)

            if 'product' in data:
                return JsonResponse({
                    'status': 'ok',
                    'ready': True,
                    'data': data
                }, safe=False)
            else:
                return JsonResponse(data, safe=False, status=500)

    if method == 'GET' and target == 'pixlr-hash':
        if 'new' in data:
            random_hash = utils.random_hash()
            pixlr_data = {'status': 'new', 'url': '', 'image_id': data.get('new')}
            cache.set('pixlr_%s' % random_hash, pixlr_data, timeout=21600) # 6 hours timeout
            pixlr_data['key'] = random_hash

        if 'check' in data:
            pixlr_key = 'pixlr_%s' % data.get('check')

            if pixlr_key not in cache:
                return JsonResponse({'error': 'Pixlr key not found.'}, status=404)

            pixlr_data = cache.get(pixlr_key)

        return JsonResponse(pixlr_data)

    if method == 'POST' and target == 'product-delete':
        try:
            product = ShopifyProduct.objects.get(id=data.get('product'))
            user.can_delete(product)
        except ShopifyProduct.DoesNotExist:
            return JsonResponse({'error': 'Product does not exists'}, status=404)

        product.userupload_set.update(product=None)
        product.delete()

        return JsonResponse({'status': 'ok'})

    if method == 'POST' and target == 'bulk-edit':
        for p in data.getlist('product'):
            product = ShopifyProduct.objects.get(id=p)
            user.can_edit(product)

            product_data = json.loads(product.data)

            product_data['title'] = data.get('title[%s]' % p)
            product_data['tags'] = data.get('tags[%s]' % p)
            product_data['price'] = utils.safeFloat(data.get('price[%s]' % p))
            product_data['compare_at_price'] = utils.safeFloat(data.get('compare_at[%s]' % p))
            product_data['type'] = data.get('type[%s]' % p)
            product_data['weight'] = data.get('weight[%s]' % p)

            product.data = json.dumps(product_data)
            product.save()

        return JsonResponse({'status': 'ok'})

    if method == 'GET' and target == 'product-shopify-id':
        ids = []
        products = data.get('product').split(',')
        for p in products:
            product = ShopifyProduct.objects.get(id=p)
            shopify_id = product.get_shopify_id()
            if shopify_id and shopify_id not in ids:
                ids.append(shopify_id)

        return JsonResponse({
            'status': 'ok',
            'ids': ids
        })

    if method == 'POST' and target == 'product-edit':
        products = []
        for p in data.getlist('products[]'):
            product = ShopifyProduct.objects.get(id=p)
            user.can_edit(product)

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

        return JsonResponse({
            'status': 'ok',
            'products': products
        }, safe=False)

    if method == 'POST' and target == 'boards-add':
        can_add, total_allowed, user_count = user.profile.can_add_board()

        if not can_add:
            return JsonResponse({
                'error': 'Your current plan allow up to %d boards, currently you have %d boards.'
                         % (total_allowed, user_count)
            })

        board_name = data.get('title', '').strip()

        if not len(board_name):
            return JsonResponse({'error': 'Board name is required'}, status=501)

        board = ShopifyBoard(title=board_name, user=user.models_user)
        user.can_add(board)

        board.save()

        return JsonResponse({
            'status': 'ok',
            'board': {
                'id': board.id,
                'title': board.title
            }
        })

    if method == 'POST' and target == 'board-add-products':
        board = ShopifyBoard.objects.get(id=data.get('board'))
        user.can_edit(board)

        for p in data.getlist('products[]'):
            product = ShopifyProduct.objects.get(id=p)
            user.can_edit(product)

            board.products.add(product)

        board.save()

        return JsonResponse({'status': 'ok'})

    if method == 'POST' and target == 'product-remove-board':
        board = ShopifyBoard.objects.get(id=data.get('board'))
        user.can_edit(board)

        for p in data.getlist('products[]'):
            product = ShopifyProduct.objects.get(id=p)
            user.can_edit(product)

            board.products.remove(product)

        board.save()

        return JsonResponse({'status': 'ok'})

    if method == 'POST' and target == 'product-board':
        product = ShopifyProduct.objects.get(id=data.get('product'))
        user.can_edit(product)

        if data.get('board') == '0':
            product.shopifyboard_set.clear()
            product.save()

            return JsonResponse({
                'status': 'ok'
            })
        else:
            board = ShopifyBoard.objects.get(id=data.get('board'))
            user.can_edit(board)

            board.products.add(product)
            board.save()

            return JsonResponse({
                'status': 'ok',
                'board': {
                    'id': board.id,
                    'title': board.title
                }
            })
    if method == 'POST' and target == 'board-delete':
        board = ShopifyBoard.objects.get(id=data.get('board'))
        user.can_delete(board)

        board.delete()

        return JsonResponse({
            'status': 'ok'
        })

    if method == 'POST' and target == 'board-empty':
        board = ShopifyBoard.objects.get(id=data.get('board'))
        user.can_edit(board)

        board.products.clear()

        return JsonResponse({
            'status': 'ok'
        })

    if method == 'POST' and target == 'variant-image':
        # TODO: Move to after boards endpoints
        try:
            store = ShopifyStore.objects.get(id=data.get('store'))
            user.can_view(store)

        except ShopifyStore.DoesNotExist:
            return JsonResponse({'error': 'Store not found'}, status=404)

        api_url = '/admin/variants/{}.json'.format(data.get('variant'))
        api_url = store.get_link(api_url, api=True)

        api_data = {
            "variant": {
                "id": data.get('variant'),
                "image_id": data.get('image'),
            }
        }

        requests.put(api_url, json=api_data)

        return JsonResponse({
            'status': 'ok'
        })

    if method == 'GET' and target == 'board-config':
        board = ShopifyBoard.objects.get(id=data.get('board'))
        user.can_edit(board)

        try:
            return JsonResponse({
                'status': 'ok',
                'title': board.title,
                'config': json.loads(board.config)
            })
        except:
            return JsonResponse({
                'status': 'ok',
                'title': board.title,
                'config': {
                    'title': '',
                    'tags': '',
                    'type': ''
                }
            })

    if method == 'POST' and target == 'board-config':
        board = ShopifyBoard.objects.get(id=data.get('board'))
        user.can_edit(board)

        board.title = data.get('store-title')

        board.config = json.dumps({
            'title': data.get('title'),
            'tags': data.get('tags'),
            'type': data.get('type'),
        })

        board.save()

        utils.smart_board_by_board(user.models_user, board)

        return JsonResponse({
            'status': 'ok'
        })

    if method == 'POST' and target == 'change-plan':
        if not user.is_superuser:
            raise PermissionDenied()

        target_user = User.objects.get(id=data.get('user'))
        plan = GroupPlan.objects.get(id=data.get('plan'))

        try:
            profile = target_user.profile
            target_user.profile.plan = plan
        except:
            profile = UserProfile(user=target_user, plan=plan)
            profile.save()

        target_user.profile.save()

        return JsonResponse({
            'status': 'ok',
            'plan': {
                'id': plan.id,
                'title': plan.title
            }
        })

    if method == 'DELETE' and target == 'access-token':
        if not user.is_superuser:
            raise PermissionDenied()

        target_user = User.objects.get(id=data.get('user'))
        for i in target_user.accesstoken_set.all():
            i.delete()

        return JsonResponse({'status': 'ok'})

    if method == 'POST' and target == 'product-notes':
        product = ShopifyProduct.objects.get(id=data.get('product'))
        user.can_edit(product)

        product.notes = data.get('notes')
        product.save()

        return JsonResponse({
            'status': 'ok',
        })

    if method == 'POST' and target == 'product-metadata':
        if not user.can('product_metadata.use'):
            return JsonResponse({'error': 'Your current plan doesn\'t have this feature.'})

        product = ShopifyProduct.objects.get(id=data.get('product'))
        user.can_edit(product)

        product.set_original_url(data.get('original-link'))

        shopify_link = data.get('shopify-link')

        if not shopify_link:
            if product.shopify_export:
                product.shopify_export = None
        else:
            if 'myshopify' not in shopify_link.lower():
                shopify_link = utils.get_myshopify_link(user, product.store, shopify_link)
                if not shopify_link:
                    return JsonResponse({'error': 'Invalid Custom domain link.'})

            shopify_id = product.set_shopify_id_from_url(shopify_link)
            if not shopify_id:
                return JsonResponse({'error': 'Invalid Shopify link.'})

            product_export = ShopifyProductExport(original_url=data.get('original-link'), shopify_id=shopify_id,
                                                  store=product.store)
            product_export.save()

            product.shopify_export = product_export

        product.save()

        return JsonResponse({
            'status': 'ok',
        })

    if method == 'POST' and target == 'add-user-upload':
        product = ShopifyProduct.objects.get(id=data.get('product'))
        user.can_edit(product)

        upload = UserUpload(user=user.models_user, product=product, url=data.get('url'))
        user.can_add(upload)

        upload.save()

        return JsonResponse({
            'status': 'ok',
        })

    if method == 'POST' and target == 'product-duplicate':
        product = ShopifyProduct.objects.get(id=data.get('product'))
        user.can_view(product)

        duplicate_product = ShopifyProduct.objects.get(id=data.get('product'))

        duplicate_product.pk = None
        duplicate_product.parent_product = product
        duplicate_product.shopify_export = None

        user.can_add(duplicate_product)

        duplicate_product.save()

        return JsonResponse({
            'status': 'ok',
            'product': {
                'id': duplicate_product.id,
                'url': reverse('product_view', args=[duplicate_product.id])
            }
        })

    if method == 'GET' and target == 'user-config':
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

        config['import'] = []
        perms = profile.get_perms
        for i in perms:
            if i.endswith('_import.use'):
                name = i.split('_')[0]
                config['import'].append(name)

        # Base64 encode the store import list
        config['import'] = json.dumps(config['import']).encode('base64').replace('\n', '')

        for k in config.keys():
            if k.startswith('_'):
                del config[k]

        return JsonResponse(config)

    if method == 'POST' and target == 'user-config':
        profile = user.models_user.profile

        try:
            config = json.loads(profile.config)
        except:
            config = {}

        form_webapp = (data.get('from', False) == 'webapp')

        if form_webapp:
            bool_config = ['make_visisble', 'epacket_shipping', 'auto_ordered_mark', 'validate_tracking_number']
        else:
            bool_config = ['make_visisble', 'epacket_shipping', 'auto_ordered_mark']

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
                    config[key] = int(data[key])
                except:
                    config[key] = ''

            elif key in ['make_visisble', 'epacket_shipping']:
                config[key] = bool(data.get(key))
                bool_config.remove(key)

            else:
                config[key] = data[key]

        for key in bool_config:
            config[key] = (key in data)

        profile.config = json.dumps(config)
        profile.save()

        return JsonResponse({'status': 'ok'})

    if method == 'POST' and target == 'fulfill-order':
        try:
            store = ShopifyStore.objects.get(id=data.get('fulfill-store'))
            user.can_view(store)

        except ShopifyStore.DoesNotExist:
            return JsonResponse({'error': 'Store not found'}, status=404)

        tracking = data.get('fulfill-traking-number')
        if not tracking:
            tracking = None

        api_data = {
            "fulfillment": {
                "tracking_number": tracking,
                "tracking_company": "Other",
                "tracking_url": "https://track.aftership.com/{}".format(tracking),
                "line_items": [{
                    "id": int(data.get('fulfill-line-id')),
                    "quantity": int(data.get('fulfill-quantity'))
                }]
            }
        }

        notify_customer = data.get('fulfill-notify-customer')
        if notify_customer and notify_customer != 'default':
            api_data['fulfillment']['notify_customer'] = (notify_customer == 'yes')

        rep = requests.post(
            url=store.get_link('/admin/orders/{}/fulfillments.json'.format(data.get('fulfill-order-id')), api=True),
            json=api_data
        )

        if 'fulfillment' in rep.json():
            return JsonResponse({'status': 'ok'})
        else:
            try:
                errors = utils.format_shopify_error(rep.json())
                return JsonResponse({'error': 'Shopify Error: {}'.format(errors)})
            except:
                return JsonResponse({'error': 'Shopify API Error'})

    if method == 'GET' and target == 'order-data':
        order_key = data.get('order')

        if not order_key.startswith('order_'):
            order_key = 'order_{}'.format(order_key)

        order = cache.get(order_key)
        if order:
            return JsonResponse(order, safe=False)
        else:
            return JsonResponse({'error': 'Not found'}, status=404)

    if method == 'GET' and target == 'product-variant-image':
        try:
            store = ShopifyStore.objects.get(id=data.get('store'))
            user.can_view(store)
        except ShopifyStore.DoesNotExist:
            return JsonResponse({'error': 'Store not found'}, status=404)

        image = utils.get_shopify_variant_image(store, data.get('product'), data.get('variant'))

        if image:
            return JsonResponse({
                'status': 'ok',
                'image': image
            })
        else:
            return JsonResponse({'error': 'Image not found'}, status=404)

    if method == 'POST' and target == 'variants-mapping':
        product = ShopifyProduct.objects.get(id=data.get('product'))
        user.can_edit(product)

        mapping = {}
        for k in data:
            if k != 'product':
                mapping[k] = data[k]

                if '/' in data[k]:
                    return JsonResponse({
                        'error': 'The character / is not allowed in variants name.\n'
                                 'It will cause issues with auto-variant selection'
                    })

        product.variants_map = json.dumps(mapping)
        product.save()

        return JsonResponse({'status': 'ok'})

    if method == 'GET' and target == 'order-fulfill':
        if int(data.get('count', 0)) >= 30:
            raise Http404('Not found')

        # Get Orders marked as Ordered
        from django.core import serializers

        orders = []
        shopify_orders = ShopifyOrderTrack.objects.filter(user=user.models_user, hidden=False) \
                                             .filter(source_tracking='') \
                                             .exclude(source_status='FINISH') \
                                             .order_by('updated_at')
        if user.is_subuser:
            shopify_orders = shopify_orders.filter(store__in=user.profile.get_active_stores(flat=True))

        if not data.get('order_id') and not data.get('line_id'):
            limit_key = 'order_fulfill_limit_%d' % user.id
            limit = cache.get(limit_key)

            if limit is None:
                limit = utils.calc_orders_limit(orders_count=shopify_orders.count())

                if limit != 20:
                    cache.set(limit_key, limit, timeout=3600)
                    print "ORDER FULFILL LIMIT: {} FOR {}".format(limit, user.username)

            shopify_orders = shopify_orders[:limit]

        if data.get('order_id'):
            shopify_orders = shopify_orders.filter(order_id=data.get('order_id'))

        if data.get('line_id'):
            shopify_orders = shopify_orders.filter(line_id=data.get('line_id'))

        shopify_orders = serializers.serialize('python', shopify_orders,
                                               fields=('id', 'order_id', 'line_id',
                                                       'source_id', 'source_status',
                                                       'source_tracking'))

        for i in shopify_orders:
            fields = i['fields']
            fields['id'] = i['pk']
            orders.append(fields)

        if not data.get('order_id') and not data.get('line_id'):
            ShopifyOrderTrack.objects.filter(user=user.models_user, id__in=[i['id'] for i in orders]) \
                                .update(check_count=F('check_count')+1, updated_at=timezone.now())

        return JsonResponse(orders, safe=False)

    if method == 'POST' and target == 'order-fulfill':
        # Mark Order as Ordered
        order_id = data.get('order_id')
        order_lines = data.get('line_id')
        source_id = data.get('aliexpress_order_id', '')

        try:
            assert len(source_id) > 0, 'Empty Order ID'
            assert re.match('^[0-9]{10,}$', source_id) is not None, 'Not a valid Aliexpress Order ID: {}'.format(source_id)
        except AssertionError as e:
            raven_client.captureMessage('Non valid Aliexpress Order ID')

            return JsonResponse({'error': e.message}, status=501)

        order_data = {
            'aliexpress': {
                'order_trade': data.get('aliexpress_order_trade')
            }
        }

        try:
            store = ShopifyStore.objects.get(id=data.get('store'))
            user.can_view(store)

        except ShopifyStore.DoesNotExist:
            raven_client.captureException()
            return JsonResponse({'error': 'Store {} not found'.format(data.get('store'))}, status=404)

        for line_id in order_lines.split(','):
            order = ShopifyOrderTrack(user=user.models_user,
                                 store=store,
                                 order_id=order_id,
                                 line_id=line_id,
                                 source_id=source_id,
                                 data=json.dumps(order_data))

            user.can_add(order)
            order.save()

            try:
                order_line = utils.get_shopify_order_line(store, order_id, line_id)
                if order_line:
                    note = u'Aliexpress Order ID: {0}\n' \
                           'http://trade.aliexpress.com/order_detail.htm?orderId={0}\n' \
                           'Shopify Product: {1} / {2}'.format(source_id, order_line.get('name'),
                                                               order_line.get('variant_title'))
                else:
                    note = 'Aliexpress Order ID: {0}\n' \
                           'http://trade.aliexpress.com/order_detail.htm?orderId={0}\n'.format(source_id)

                utils.add_shopify_order_note(store, order_id, note)
            except:
                raven_client.captureException(level='warning')

        return JsonResponse({'status': 'ok'})

    if method == 'DELETE' and target == 'order-fulfill':
        order_id = data.get('order_id')
        line_id = data.get('line_id')

        orders = ShopifyOrderTrack.objects.filter(user=user.models_user, order_id=order_id, line_id=line_id)

        if orders.count():
            for order in orders:
                user.can_delete(order)
                order.delete()

            return JsonResponse({'status': 'ok'})
        else:
            return JsonResponse({'error': 'Order not found.'}, status=404)

    if method == 'POST' and target == 'order-fulfill-update':
        order = ShopifyOrderTrack.objects.get(id=data.get('order'))
        user.can_edit(order)

        order.source_status = data.get('status')
        order.source_tracking = data.get('tracking_number')
        order.status_updated_at = timezone.now()

        try:
            order_data = json.loads(order.data)
            if 'aliexpress' not in order_data:
                order_data['aliexpress'] = {}
        except:
            order_data = {'aliexpress': {}}

        order_data['aliexpress']['end_reason'] = data.get('end_reason')
        order.data = json.dumps(order_data)

        order.save()

        return JsonResponse({'status': 'ok'})

    if method == 'GET' and target == 'auto-fulfill-count':
        time_now = timezone.now()
        if data.get('threshold') in ['hour', 'hourly']:
            time_threshold = time_now - timezone.timedelta(hours=1)
        elif data.get('threshold') in ['day', 'daily']:
            time_threshold = time_now - timezone.timedelta(days=1)
        elif data.get('threshold') == 'any':
            time_threshold = None
        else:
            return JsonResponse({'error': 'Threshold is not properly set.'}, status=500)

        orders = ShopifyOrderTrack.objects.exclude(shopify_status='fulfilled').exclude(source_tracking='')

        if user.is_superuser:
            if 'user' in data:
                if data.get('user') != 'all':
                    orders = orders.filter(id__in=User.objects.get(id=data.get('user')).shopifystore_set.all())
            else:
                orders = orders.filter(id__in=user.shopifystore_set.all())
        else:
            orders = orders.filter(id__in=user.models_user.shopifystore_set.all())

        if time_threshold:
            orders = orders.filter(status_updated_at__lt=time_threshold)

        return JsonResponse({
            'status': 'ok',
            'count': orders.count()
        })

    if method == 'POST' and target == 'order-add-note':
        # Append to the Order note
        store = ShopifyStore.objects.get(id=data.get('store'))
        user.can_view(store)

        if utils.add_shopify_order_note(store, data.get('order_id'), data.get('note')):
            return JsonResponse({'status': 'ok'})
        else:
            return JsonResponse({'error': 'Shopify API Error'}, status=500)

    if method == 'POST' and target == 'order-note':
        # Change the Order note
        store = ShopifyStore.objects.get(id=data.get('store'))
        user.can_view(store)

        if utils.set_shopify_order_note(store, data.get('order_id'), data['note']):
            return JsonResponse({'status': 'ok'})
        else:
            return JsonResponse({'error': 'Shopify API Error'}, status=500)

    if method == 'POST' and target == 'order-fullfill-hide':
        order = ShopifyOrderTrack.objects.get(id=data.get('order'))
        user.can_edit(order)

        order.hidden = data.get('hide', False)
        order.save()

        return JsonResponse({'status': 'ok'})

    if method == 'GET' and target == 'find-product':
        try:
            product = ShopifyProduct.objects.get(shopify_export__shopify_id=data.get('product'))
            user.can_view(product)

            return JsonResponse({
                'status': 'ok',
                'url': 'https://app.shopifiedapp.com{}'.format(reverse('product_view', args=[product.id]))
            })
        except:
            return JsonResponse({'error': 'Product not found'}, status=404)

    if method == 'POST' and target == 'generate-reg-link':
        if not user.is_superuser and not user.has_perm('leadgalaxy.add_planregistration'):
            return JsonResponse({'error': 'Unauthorized API call'}, status=403)

        plan_id = int(data.get('plan'))
        if not user.is_superuser and plan_id != 8:
            return JsonResponse({'error': 'Unauthorized API call'}, status=403)

        plan = GroupPlan.objects.get(id=plan_id)
        reg = utils.generate_plan_registration(plan, {
            'email': data.get('email')
        })

        return JsonResponse({
            'status': 'ok',
            'hash': reg.register_hash
        })

    if method == 'GET' and target == 'product-original-desc':
        try:
            product = ShopifyProduct.objects.get(id=data.get('product'))
            user.can_view(product)

            return HttpResponse(json.loads(product.original_data)['description'])
        except:
            return HttpResponse('')

    if method == 'GET' and target == 'timezones':
        return JsonResponse(utils.get_timezones(data.get('country')), safe=False)

    if method == 'POST' and target == 'user-profile':
        form = UserProfileForm(data)
        if form.is_valid():
            user.first_name = form.cleaned_data['first_name']
            user.last_name = form.cleaned_data['last_name']
            user.save()

            profile = user.profile
            profile.timezone = form.cleaned_data['timezone']
            profile.country = form.cleaned_data['country']
            profile.save()

            request.session['django_timezone'] = form.cleaned_data['timezone']

            return JsonResponse({'status': 'ok', 'reload': True})

    if method == 'POST' and target == 'user-email':
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

            return JsonResponse({
                'status': 'ok',
                'email': email_change,
                'password': password
            })
        else:
            return JsonResponse({'error': form.errors})

    if method == 'GET' and target == 'shipping-aliexpress':
        aliexpress_id = data.get('id')

        country_code = data.get('country', 'US')
        if country_code == 'GB':
            country_code = 'UK'

        data = utils.aliexpress_shipping_info(aliexpress_id, country_code)
        return JsonResponse(data, safe=False)

    if method == 'POST' and target == 'subuser-delete':
        try:
            subuser = User.objects.get(id=data.get('subuser'), profile__subuser_parent=user)
        except User.DoesNotExist:
            return JsonResponse({'error': 'User not found'}, status=404)
        except:
            return JsonResponse({'error': 'Unknown Error'}, status=500)

        profile = subuser.profile

        profile.subuser_parent = None
        profile.subuser_stores.clear()
        profile.plan = utils.get_plan(plan_hash='606bd8eb8cb148c28c4c022a43f0432d')
        profile.save()

        AccessToken.objects.filter(user=subuser).delete()

        return JsonResponse({'status': 'ok'})

    if method == 'POST' and target == 'subuser-invite':
        if not user.can('sub_users.use'):
            raise PermissionDenied('Sub User Invite')

        if not EmailForm({'email': data.get('email')}).is_valid():
            return JsonResponse({'error': 'Email is not valid'}, status=501)

        if User.objects.filter(email__iexact=data.get('email')).count():
            return JsonResponse({'error': 'Email is is already registered to an account'}, status=501)

        if PlanRegistration.objects.filter(email__iexact=data.get('email')).count():
            return JsonResponse({'error': 'An Invitation is already sent to this email'}, status=501)

        plan = utils.get_plan(plan_slug='subuser-plan')
        reg = utils.generate_plan_registration(plan=plan, sender=user, data={
            'email': data.get('email')
        })

        data = {
            'email': data.get('email'),
            'sender': user,
            'reg_hash': reg.register_hash
        }

        template_file = os.path.join(settings.BASE_DIR, 'app', 'data', 'emails', 'subuser_invite.html')
        template = Template(open(template_file).read())

        ctx = Context(data)

        email_html = template.render(ctx)
        email_html = email_html.replace('\n', '<br />')

        send_mail(subject='Invitation to join Shopified App',
                  recipient_list=[data['email']],
                  from_email='support@shopifiedapp.com',
                  message=email_html,
                  html_message=email_html)

        return JsonResponse({
            'status': 'ok',
            'hash': reg.register_hash
        })

    if method == 'POST' and target == 'alert-archive':
        try:
            alert = AliexpressProductChange.objects.get(id=data.get('alert'))
            user.can_edit(alert)

            alert.hidden = 1
            alert.save()
        except User.DoesNotExist:
            return JsonResponse({'error': 'User not found'}, status=404)

        return JsonResponse({
            'status': 'ok'
        })

    raven_client.captureMessage('Non-handled endpoint')
    return JsonResponse({'error': 'Non-handled endpoint'}, status=501)


def webhook(request, provider, option):
    if provider == 'paylio' and request.method == 'POST':
        if option not in ['vip-elite', 'elite', 'pro', 'basic']:
            return JsonResponse({'error': 'Unknown Plan'}, status=404)

        plan_map = {
            'vip-elite': '64543a8eb189bae7f9abc580cfc00f76',
            'elite': '3eccff4f178db4b85ff7245373102aec',
            'pro': '55cb8a0ddbc9dacab8d99ac7ecaae00b',
            'basic': '2877056b74f4683ee0cf9724b128e27b',
            'free': '606bd8eb8cb148c28c4c022a43f0432d'
        }

        plan = GroupPlan.objects.get(register_hash=plan_map[option])

        if 'payer_email' not in request.POST:
            return HttpResponse('ok')

        try:
            status = request.POST['status']
            if status not in ['new', 'canceled', 'refunded']:
                raise Exception('Unknown Order status: {}'.format(status))

            data = {
                'email': request.POST['payer_email'],
                'status': status,
                'lastname': request.POST['payer_lastname'],
                'firstname': request.POST['payer_firstname'],
                'payer_id': request.POST['payer_id'],
            }
        except Exception as e:
            raven_client.captureException()

            send_mail(subject='Shopified App: Webhook exception',
                      recipient_list=['chase@shopifiedapp.com', 'ma7dev@gmail.com'],
                      from_email=settings.DEFAULT_FROM_EMAIL,
                      message='EXCEPTION: {}\nGET:\n{}\nPOST:\n{}\nMETA:\n{}'.format(
                              traceback.format_exc(),
                              utils.format_data(dict(request.GET.iteritems()), False),
                              utils.format_data(dict(request.POST.iteritems()), False),
                              utils.format_data(request.META, False)))

            raise Http404('Error during proccess')

        if status == 'new':
            reg = utils.generate_plan_registration(plan, data)
            data['reg_hash'] = reg.register_hash
            data['plan_title'] = plan.title

            template_file = os.path.join(settings.BASE_DIR, 'app', 'data', 'emails', 'webhook_register.html')
            template = Template(open(template_file).read())

            ctx = Context(data)

            email_html = template.render(ctx)
            email_html = email_html.replace('\n', '<br />')

            send_mail(subject='Your Shopified App Access',
                      recipient_list=[data['email']],
                      from_email='support@shopifiedapp.com',
                      message=email_html,
                      html_message=email_html)

            utils.slack_invite(data)

            send_mail(subject='Shopified App: New Registration',
                      recipient_list=['chase@shopifiedapp.com'],
                      from_email=settings.DEFAULT_FROM_EMAIL,
                      message='A new registration link was generated and send to a new user.\n\nMore information:\n{}'.format(
                          utils.format_data(data)))

            return HttpResponse('ok')
        elif status in ['canceled', 'refunded']:
            try:
                user = User.objects.get(email__iexact=data['email'])

                free_plan = GroupPlan.objects.get(register_hash=plan_map['free'])
                user.profile.plan = free_plan
                user.profile.save()

                data['previous_plan'] = plan.title
                data['new_plan'] = free_plan.title

                send_mail(subject='Shopified App: Cancel/Refund',
                          recipient_list=['chase@shopifiedapp.com'],
                          from_email=settings.DEFAULT_FROM_EMAIL,
                          message='A Shopified App User has canceled his/her subscription.\n\nMore information:\n{}'.format(
                              utils.format_data(data)))

                return HttpResponse('ok')

            except Exception as e:
                raven_client.captureException()

                send_mail(subject='Shopified App: Webhook Cancel/Refund exception',
                          recipient_list=['chase@shopifiedapp.com', 'ma7dev@gmail.com'],
                          from_email=settings.DEFAULT_FROM_EMAIL,
                          message='EXCEPTION: {}\nGET:\n{}\nPOST:\n{}\nMETA:\n{}'.format(
                              traceback.format_exc(),
                              utils.format_data(dict(request.GET.iteritems()), False),
                              utils.format_data(dict(request.POST.iteritems()), False),
                              utils.format_data(request.META, False)))

                raise Http404('Error during proccess')

    elif provider == 'jvzoo':
        try:
            if ':' not in option and option not in ['vip-elite', 'elite', 'pro', 'basic']:
                return JsonResponse({'error': 'Unknown Plan'}, status=404)

            plan_map = {
                'vip-elite': '64543a8eb189bae7f9abc580cfc00f76',
                'elite': '3eccff4f178db4b85ff7245373102aec',
                'pro': '55cb8a0ddbc9dacab8d99ac7ecaae00b',
                'basic': '2877056b74f4683ee0cf9724b128e27b',
                'free': '606bd8eb8cb148c28c4c022a43f0432d'
            }

            plan = None
            bundle = None

            if ':' in option:
                option_type, option_title = option.split(':')
                if option_type == 'bundle':
                    bundle = FeatureBundle.objects.get(slug=option_title)
                elif option_type == 'plan':
                    plan = GroupPlan.objects.get(slug=option_title)
            else:
                # Before bundles, option is the plan slug
                plan = GroupPlan.objects.get(register_hash=plan_map[option])

            if request.method == 'GET':
                webhook_type = 'Plan'
                if bundle:
                    webhook_type = 'Bundle'

                if not request.user.is_superuser:
                    return JsonResponse({'status': 'ok'})
                else:
                    return HttpResponse('<i>JVZoo</i> Webhook for <b><span style=color:green>{}</span>: {}</b>'
                                        .format(webhook_type, (bundle.title if bundle else plan.title)))

            elif request.method != 'POST':
                raise Exception('Unexpected HTTP Method: {}'.request.method)

            params = dict(request.POST.iteritems())
            secretkey = settings.JVZOO_SECRET_KEY

            # verify and parse post
            utils.jvzoo_verify_post(params, secretkey)
            data = utils.jvzoo_parse_post(params)

            trans_type = data['trans_type']
            if trans_type not in ['SALE', 'BILL', 'RFND', 'CANCEL-REBILL', 'CGBK', 'INSF']:
                raise Exception('Unknown Transaction Type: {}'.format(trans_type))

            if trans_type == 'SALE':
                if plan:
                    data['jvzoo'] = params

                    expire = request.GET.get('expire')
                    if expire:
                        if expire != '1y':
                            raven_client.captureMessage('Unsupported Expire format',
                                                        extra={'expire': expire})

                        expire_date = timezone.now() + timezone.timedelta(days=365)
                        data['expire_date'] = expire_date.isoformat()
                        data['expire_param'] = expire

                    reg = utils.generate_plan_registration(plan, data)

                    data['reg_hash'] = reg.register_hash
                    data['plan_title'] = plan.title

                    try:
                        user = User.objects.get(email__iexact=data['email'])
                        print 'WARNING: JVZOO SALE UPGARDING: {} to {}'.format(data['email'], plan.title)
                    except User.DoesNotExist:
                        user = None
                    except Exception:
                        raven_client.captureException()
                        user = None

                    if user:
                        user.profile.apply_registration(reg)
                    else:
                        utils.send_email_from_template(tpl='webhook_register.html',
                                                       subject='Your Shopified App Access',
                                                       recipient=data['email'],
                                                       data=data)

                else:
                    # Handle bundle purchase
                    data['bundle_title'] = bundle.title

                    data['jvzoo'] = params
                    reg = utils.generate_plan_registration(plan=None, bundle=bundle, data=data)

                    try:
                        user = User.objects.get(email__iexact=data['email'])
                        user.profile.apply_registration(reg)
                    except User.DoesNotExist:
                        user = None

                    utils.send_email_from_template(tpl='webhook_bundle_purchase.html',
                                                   subject='[Shopified App] You Have Been Upgraded To {}'.format(bundle.title),
                                                   recipient=data['email'],
                                                   data=data)

                data.update(params)

                tasks.invite_user_to_slack.delay(slack_teams=request.GET.get('slack', 'users'), data=data)

                smartmemeber = request.GET.get('sm')
                if smartmemeber:
                    tasks.smartmemeber_webhook_call.delay(subdomain=smartmemeber, data=params)

                payment = PlanPayment(fullname=data['fullname'],
                                      email=data['email'],
                                      provider='JVZoo',
                                      transaction_type=trans_type,
                                      payment_id=params['ctransreceipt'],
                                      data=json.dumps(data))
                payment.save()

                tags = {'trans_type': trans_type}
                if plan:
                    tags['sale_type'] = 'Plan'
                    tags['sale_title'] = plan.title
                else:
                    tags['sale_type'] = 'Bundle'
                    tags['sale_title'] = bundle.title

                raven_client.captureMessage('JVZoo New Purchase',
                                            extra={'name': data['fullname'], 'email': data['email'],
                                                   'trans_type': trans_type, 'payment': payment.id},
                                            tags=tags,
                                            level='info')

                return JsonResponse({'status': 'ok'})

            elif trans_type == 'BILL':
                data['jvzoo'] = params
                payment = PlanPayment(fullname=data['fullname'],
                                      email=data['email'],
                                      provider='JVZoo',
                                      transaction_type=trans_type,
                                      payment_id=params['ctransreceipt'],
                                      data=json.dumps(data))
                payment.save()

            elif trans_type in ['RFND', 'CANCEL-REBILL', 'CGBK', 'INSF']:
                try:
                    user = User.objects.get(email__iexact=data['email'])
                except User.DoesNotExist:
                    user = None

                new_refund = PlanPayment.objects.filter(payment_id=params['ctransreceipt'],
                                                        transaction_type=trans_type).count() == 0

                if new_refund:
                    if user:
                        if plan:
                            free_plan = GroupPlan.objects.get(register_hash=plan_map['free'])
                            user.profile.plan = free_plan
                            user.profile.save()

                            data['previous_plan'] = plan.title
                            data['new_plan'] = free_plan.title
                        elif bundle:
                            data['removed_bundle'] = bundle.title
                            user.profile.bundles.remove(bundle)
                    else:
                        PlanRegistration.objects.filter(plan=plan, bundle=bundle, email__iexact=data['email']) \
                                                .update(expired=True)

                data['new_refund'] = new_refund
                data['jvzoo'] = params

                payment = PlanPayment(fullname=data['fullname'],
                                      email=data['email'],
                                      user=user,
                                      provider='JVZoo',
                                      transaction_type=trans_type,
                                      payment_id=params['ctransreceipt'],
                                      data=json.dumps(data))
                payment.save()

                if new_refund:
                    raven_client.captureMessage('JVZoo User Cancel/Refund',
                                                extra={'name': data['fullname'], 'email': data['email'],
                                                       'trans_type': trans_type, 'payment': payment.id},
                                                tags={'trans_type': trans_type},
                                                level='info')

                return JsonResponse({'status': 'ok'})

        except Exception:
            raven_client.captureException()
            return JsonResponse({'error': 'Server Error'}, status=500)

        return JsonResponse({'status': 'ok', 'warning': 'Unknown'})

    elif provider == 'shopify' and request.method == 'POST':
        try:
            token = request.GET['t']
            topic = option.replace('-', '/')
            store = ShopifyStore.objects.get(id=request.GET['store'])

            if token != utils.webhook_token(store.id):
                raise Exception('Unvalide token: {} <> {}'.format(
                    token, utils.webhook_token(store.id)))

            if 'products' in topic:
                # Shopify send a JSON POST request
                shopify_product = json.loads(request.body)
                product = None
                try:
                    product = ShopifyProduct.objects.get(
                        user=store.user,
                        shopify_export__shopify_id=shopify_product['id'])
                except:
                    return JsonResponse({'status': 'ok', 'warning': 'Processing exception'})

                product_data = json.loads(product.data)
            elif 'orders' in topic:
                shopify_order = json.loads(request.body)
            else:
                raven_client.captureMessage('Non-handled Shopify Topic',
                                            extra={'topic': topic, 'store': store})

                return JsonResponse({'status': 'ok', 'warning': 'Non-handled Topic'})

            if topic == 'products/update':
                product_data['title'] = shopify_product['title']
                product_data['type'] = shopify_product['product_type']
                product_data['tags'] = shopify_product['tags']
                product_data['images'] = [i['src'] for i in shopify_product['images']]

                prices = [i['price'] for i in shopify_product['variants']]
                compare_at_prices = [i['compare_at_price'] for i in shopify_product['variants']]

                if len(set(prices)) == 1:  # If all variants have the same price
                    product_data['price'] = utils.safeFloat(prices[0])

                if len(set(compare_at_prices)) == 1:  # If all variants have the same compare at price
                    product_data['compare_at_price'] = utils.safeFloat(compare_at_prices[0])

                product.data = json.dumps(product_data)
                product.save()

                ShopifyWebhook.objects.filter(token=token, store=store, topic=topic) \
                                      .update(call_count=F('call_count')+1)

                # Delete Product images cache
                ShopifyProductImage.objects.filter(store=store,
                                                   product=shopify_product['id']).delete()

                return JsonResponse({'status': 'ok'})

            elif topic == 'products/delete':
                try:
                    if product.shopify_export:
                        product.shopify_export.delete()
                except ShopifyProductExport.DoesNotExist:
                    pass

                ShopifyWebhook.objects.filter(token=token, store=store, topic=topic) \
                                      .update(call_count=F('call_count')+1)

                ShopifyProductImage.objects.filter(store=store,
                                                   product=shopify_product['id']).delete()

                return JsonResponse({'status': 'ok'})

            elif topic == 'orders/updated':
                for line in shopify_order['line_items']:
                    fulfillment_status = line['fulfillment_status']
                    if not fulfillment_status:
                        fulfillment_status = ''

                    ShopifyOrderTrack.objects.filter(order_id=shopify_order['id'], line_id=line['id']) \
                                        .update(shopify_status=fulfillment_status)

                    ShopifyWebhook.objects.filter(token=token, store=store, topic=topic) \
                                          .update(call_count=F('call_count')+1)

                try:
                    shopify_orders_utils.update_shopify_order(store, shopify_order)
                except AssertionError:
                    raven_client.captureMessage('Store is being imported', extra={'store': store})
                    return JsonResponse({'error': 'Store Still in Process'}, status=500)
                except:
                    order_key = utils.random_hash()
                    cache.set(order_key, shopify_order, timeout=259200)

                    raven_client.captureException(extra={
                        'store': store,
                        'order_id': shopify_order.get('id'),
                        'order_key': order_key
                    })

                return JsonResponse({'status': 'ok'})

            elif topic == 'orders/delete':
                shopify_orders_utils.delete_shopify_order(store, shopify_order)
                return JsonResponse({'status': 'ok'})

            else:
                raise Exception('WEBHOOK: options not found: {}'.format(topic))
        except:
            raven_client.captureException()

            return JsonResponse({'status': 'ok', 'warning': 'Processing exception'})

    elif provider == 'price-notification' and request.method == 'POST':
        product_id = request.GET['product']
        try:
            product = ShopifyProduct.objects.get(id=product_id)
        except ShopifyProduct.DoesNotExist:
            return JsonResponse({'error': 'Product Not Found'}, status=404)

        product_change = AliexpressProductChange(product=product, user=product.user, data=request.body)
        product_change.save()

        utils.product_change_notify(product.user)

        return JsonResponse({'status': 'ok'})

    else:
        return JsonResponse({'status': 'ok', 'warning': 'Unknown provider'})


def get_product(request, filter_products, post_per_page=25, sort=None, store=None, board=None, load_boards=False):
    products = []
    paginator = None
    page = request.GET.get('page', 1)
    models_user = request.user.models_user
    user = request.user
    user_stores = request.user.profile.get_active_stores(flat=True)
    res = ShopifyProduct.objects.select_related('store', 'shopify_export') \
                                .filter(user=models_user).filter(Q(store__in=user_stores) | Q(store=None))
    if store:
        if store == 'c':  # connected
            res = res.exclude(shopify_export__isnull=True)
        elif store == 'n':  # non-connected
            res = res.filter(shopify_export__isnull=True)
        else:
            store = utils.safeInt(store)
            res = res.filter(shopify_export__store=store)

            user.can_view(get_object_or_404(ShopifyStore, id=store))

    if board:
        res = res.filter(shopifyboard=board)
        user.can_view(get_object_or_404(ShopifyBoard, id=board))

    if not filter_products and not sort:
        paginator = utils.SimplePaginator(res, post_per_page)

        page = min(max(1, utils.safeInt(page)), paginator.num_pages)
        page = paginator.page(page)
        res = page

    for i in res:
        p = {
            'qelem': i,
            'id': i.id,
            'store': i.store,
            'shopify_url': i.shopify_link(),
            'created_at': i.created_at,
            'updated_at': i.updated_at,
            'product': json.loads(i.data),
        }

        try:
            p['source'] = i.get_original_info(url=p['product']['original_url'])['source']
        except:
            pass

        p['price'] = '$%.02f' % utils.safeFloat(p['product'].get('price'))

        if 'images' not in p['product'] or not p['product']['images']:
            p['product']['images'] = []

        p['images'] = p['product']['images']

        if (filter_products):
            if accept_product(p, request.GET):
                products.append(p)
        else:
            products.append(p)

    if len(products):
        if sort:
            products = sorted_products(products, sort)

        if filter_products or sort:
            paginator = utils.SimplePaginator(products, post_per_page)

            page = min(max(1, int(page)), paginator.num_pages)
            page = paginator.page(page)

            products = page.object_list

    if load_boards and len(products):
        link_product_board(products, request.user.get_boards())

    return products, paginator, page


def link_product_board(products, boards):

    fetch_list = ['p%d-%s' % (i['id'], i['qelem'].updated_at) for i in products]

    for i in boards:
        fetch_list.append('b%d-%s' % (i.id, i.updated_at))

    fetch_key = 'link_product_board_%s' % utils.hash_text(reduce(lambda x, y: '{}.{}'.format(x, y), fetch_list))

    boards = cache.get(fetch_key)
    if boards is None:
        fetched = ShopifyProduct.objects.prefetch_related('shopifyboard_set') \
                                        .only('id') \
                                        .filter(id__in=[i['id'] for i in products])

        boards = {}
        for i in fetched:
            board = i.shopifyboard_set.first()
            boards[i.id] = {'title': board.title} if board else None

        cache.set(fetch_key, boards, timeout=3600)

    for i, v in enumerate(products):
        products[i]['board'] = boards.get(v['id'])

    return products


def accept_product(product, fdata):
    accept = True

    if fdata.get('title'):
        accept = fdata.get('title').lower() in product['product']['title'].lower()

    if fdata.get('price_min') or fdata.get('price_max'):
        price = utils.safeFloat(product['product'].get('price'))
        min_price = utils.safeFloat(fdata.get('price_min'), -1)
        max_price = utils.safeFloat(fdata.get('price_max'), -1)

        if (min_price > 0 and max_price > 0):
            accept = (accept and (min_price <= price) and (price <= max_price))
        elif (min_price > 0):
            accept = (accept and (min_price <= price))

        elif (max_price > 0):
            accept = (accept and (max_price >= price))

    if fdata.get('type'):
        accept = (accept and fdata.get('type').lower() in product['product'].get('type').lower())

    if fdata.get('tag'):
        accept = (accept and fdata.get('tag').lower() in product['product'].get('tags').lower())
    if fdata.get('visibile'):
        published = (fdata.get('visibile').lower() == 'yes')
        accept = (accept and published == bool(product['product'].get('published')))

    return accept


def sorted_products(products, sort):
    sort_reversed = (sort[0] == '-')

    if sort_reversed:
        sort = sort[1:]

    if sort == 'title':
        products = sorted(products,
                          cmp=lambda x, y: cmp(x['product']['title'], y['product']['title']),
                          reverse=sort_reversed)

    elif sort == 'price':
        products = sorted(products,
                          cmp=lambda x, y: cmp(utils.safeFloat(x['product'].get('price')),
                                               utils.safeFloat(y['product'].get('price'))),
                          reverse=sort_reversed)

    return products


@login_required
def products_list(request, tpl='grid'):
    store = request.GET.get('store', 'n')

    args = {
        'request': request,
        'filter_products': (request.GET.get('f') == '1'),
        'post_per_page': utils.safeInt(request.GET.get('ppp'), 25),
        'sort': request.GET.get('sort'),
        'store': store,
        'load_boards': (tpl is None or tpl == 'grid'),
    }

    if args['filter_products'] and not request.user.can('product_filters.use'):
        return render(request, 'upgrade.html')

    products, paginator, page = get_product(**args)

    if not tpl or tpl == 'grid':
        tpl = 'product.html'
    else:
        tpl = 'product_table.html'

    try:
        store = ShopifyStore.objects.get(id=utils.safeInt(store))
    except:
        store = None

    return render(request, tpl, {
        'paginator': paginator,
        'current_page': page,
        'filter_products': args['filter_products'],
        'products': products,
        'store': store,
        'page': 'product',
        'breadcrumbs': ['Products']
    })


@login_required
def product_view(request, pid):
    #  AWS
    import base64
    import hmac
    from hashlib import sha1

    AWS_ACCESS_KEY = os.environ.get('AWS_ACCESS_KEY_ID', '')
    AWS_SECRET_KEY = os.environ.get('AWS_SECRET_ACCESS_KEY', '')
    S3_BUCKET = os.environ.get('S3_BUCKET_NAME', '')

    aws_available = (AWS_ACCESS_KEY and AWS_SECRET_KEY and S3_BUCKET)

    conditions = [
        ["starts-with", "$utf8", ""],
        # Change this path if you need, but adjust the javascript config
        ["starts-with", "$key", "uploads"],
        ["starts-with", "$name", ""],
        ["starts-with", "$Content-Type", "image/"],
        ["starts-with", "$filename", ""],
        {"bucket": S3_BUCKET},
        {"acl": "public-read"}
    ]

    policy = {
        # Valid for 3 hours. Change according to your needs
        "expiration": arrow.now().replace(hours=+3).format("YYYY-MM-DDTHH:mm:ss") + 'Z',
        "conditions": conditions
    }

    policy_str = json.dumps(policy)
    string_to_sign = base64.encodestring(policy_str).replace('\n', '')

    signature = base64.encodestring(
        hmac.new(AWS_SECRET_KEY.encode(), string_to_sign.encode('utf8'), sha1).digest()).strip()

    #  /AWS
    if request.user.is_superuser:
        product = get_object_or_404(ShopifyProduct, id=pid)
        if product.user != request.user:
            messages.warning(request, 'Preview Mode: Other features (like Variant Mapping,'
                                      ' Product info Tab, etc) will not work.')
    else:
        product = get_object_or_404(ShopifyProduct, id=pid)
        request.user.can_view(product)

    p = {
        'qelem': product,
        'id': product.id,
        'store': product.store,
        'user': product.user,
        'created_at': product.created_at,
        'updated_at': product.updated_at,
        'data': product.data,
        'product': json.loads(product.data),
        'notes': product.notes,
    }

    if 'images' not in p['product'] or not p['product']['images']:
        p['product']['images'] = []

    p['price'] = '$%.02f' % utils.safeFloat(p['product'].get('price'))

    p['images'] = p['product']['images']
    p['original_url'] = p['product'].get('original_url')

    if (p['original_url'] and len(p['original_url'])):
        if 'aliexpress' in p['original_url'].lower():
            try:
                p['original_product_id'] = re.findall('([0-9]+).html', p['original_url'])[0]
                p['original_product_source'] = 'ALIEXPRESS'
            except:
                pass

    p['source'] = product.get_original_info()

    original = None
    try:
        original = json.loads(product.original_data)
    except:
        pass

    shopify_product = None
    export = product.shopify_export
    if export and export.shopify_id:
        p['shopify_url'] = export.store.get_link('/admin/products/{}'.format(export.shopify_id))
        p['variant_edit'] = '/product/variants/{}/{}'.format(export.store.id, export.shopify_id)

        shopify_product = utils.get_shopify_product(product.store, export.shopify_id)

        if shopify_product:
            shopify_product = utils.link_product_images(shopify_product)

    return render(request, 'product_view.html', {
        'product': p,
        'original': original,
        'shopify_product': shopify_product,
        'aws_available': aws_available or True,
        'aws_policy': string_to_sign,
        'aws_signature': signature,
        'aws_key': AWS_ACCESS_KEY,
        'aws_bucket': S3_BUCKET,
        'page': 'product',
        'breadcrumbs': [{'title': 'Products', 'url': '/product'}, 'View']
    })


@login_required
def variants_edit(request, store_id, pid):
    """
    pid: Shopify Product ID
    """

    if not request.user.can('product_variant_setup.use'):
        return render(request, 'upgrade.html')

    store = get_object_or_404(ShopifyStore, id=store_id)
    request.user.can_view(store)

    product = utils.get_shopify_product(store, pid)

    if not product:
        messages.error(request, 'Product not found in Shopify')
        return HttpResponseRedirect('/')

    return render(request, 'variants_edit.html', {
        'store': store,
        'product_id': pid,
        'product': product,
        'api_url': store.get_api_url(True),
        'page': 'product',
        'breadcrumbs': [{'title': 'Products', 'url': '/product'}, 'Edit Variants']
    })


@login_required
def product_mapping(request, store_id, product_id):
    product = get_object_or_404(ShopifyProduct, id=product_id)
    request.user.can_edit(product)

    shopify_id = product.get_shopify_id()
    if not shopify_id:
        raise Http404("Product doesn't exists on Shopify Store.")

    shopify_product = utils.get_shopify_product(product.store, shopify_id)
    if not shopify_product:
        messages.error(request, 'Product not found in Shopify')
        return HttpResponseRedirect('/')

    source_variants = []
    images = {}
    variants_map = {}

    try:
        variants_map = json.loads(product.variants_map)
    except:
        pass

    for i in shopify_product['images']:
        for var in i['variant_ids']:
            images[var] = i['src']

    for i, v in enumerate(shopify_product['variants']):
        shopify_product['variants'][i]['image'] = images.get(v['id'])

        mapped = variants_map.get(str(v['id']))
        if mapped:
            options = mapped.split(',')
        else:
            options = []
            if v.get('option1') and v.get('option1').lower() != 'default title':
                options.append(v.get('option1'))
            if v.get('option2'):
                options.append(v.get('option2'))
            if v.get('option3'):
                options.append(v.get('option3'))

        for o in options:
            source_variants.append(o)

        shopify_product['variants'][i]['default'] = ','.join(options)

    try:
        original_data = json.loads(product.original_data)
        if not original_data['variants']:
            original_data = json.loads(product.data)

        for i in [v['values'] for v in original_data['variants']]:
            for j in i:
                source_variants.append(j)
    except:
        pass

    return render(request, 'product_mapping.html', {
        'store': product.store,
        'product_id': product_id,
        'product': product,
        'shopify_product': shopify_product,
        'source_variants': json.dumps(list(set(source_variants))),
        'page': 'product',
        'breadcrumbs': [{'title': 'Products', 'url': '/product'}, 'Variants Mapping']
    })


@login_required
def bulk_edit(request):
    if not request.user.can('bulk_editing.use'):
        return render(request, 'upgrade.html')

    args = {
        'request': request,
        'filter_products': (request.GET.get('f') == '1'),
        'post_per_page': utils.safeInt(request.GET.get('ppp'), 25),
        'sort': request.GET.get('sort'),
        'store': 'n'
    }

    if args['filter_products'] and not request.user.can('product_filters.use'):
        return render(request, 'upgrade.html')

    products, paginator, page = get_product(**args)

    return render(request, 'bulk_edit.html', {
        'products': products,
        'paginator': paginator,
        'current_page': page,
        'filter_products': args['filter_products'],
        'page': 'bulk',
        'breadcrumbs': [{'title': 'Products', 'url': '/product'}, 'Bulk Edit']
    })


@login_required
def boards_list(request):
    boards = request.user.models_user.shopifyboard_set.all()

    return render(request, 'boards_list.html', {
        'boards': boards,
        'page': 'boards',
        'breadcrumbs': ['Boards']
    })


@login_required
def boards(request, board_id):
    board = get_object_or_404(ShopifyBoard, id=board_id)
    request.user.can_view(board)

    args = {
        'request': request,
        'filter_products': (request.GET.get('f') == '1'),
        'post_per_page': utils.safeInt(request.GET.get('ppp'), 25),
        'sort': request.GET.get('sort'),
        'board': board.id
    }

    products, paginator, page = get_product(**args)

    board = {
        'id': board.id,
        'title': board.title,
        'products': products
    }

    return render(request, 'boards.html', {
        'board': board,
        'paginator': paginator,
        'current_page': page,
        'searchable': True,
        'page': 'boards',
        'breadcrumbs': [{'title': 'Boards', 'url': reverse(boards_list)}, board['title']]
    })


def get_shipping_info(request):
    aliexpress_id = request.GET.get('id')
    product = request.GET.get('product')

    country_code = request.GET.get('country', 'US')
    if country_code == 'GB':
        country_code = 'UK'

    try:
        shippement_data = utils.aliexpress_shipping_info(aliexpress_id, country_code)
    except requests.Timeout:
        raven_client.context.merge(raven_client.get_data_from_request(request))
        raven_client.captureException()
        raven_client.context.clear()

        if request.GET.get('type') == 'json':
            return JsonResponse({'error': 'Aliexpress Server Timeout'}, status=501)
        else:
            return render(request, '500.html', status=500)

    if request.GET.get('type') == 'json':
        return JsonResponse(shippement_data, safe=False)

    if not request.user.is_authenticated():
        from urllib import urlencode

        return HttpResponseRedirect('%s?%s' % (reverse('django.contrib.auth.views.login'),
                                               urlencode({'next': request.get_full_path()})))

    product = get_object_or_404(ShopifyProduct, id=request.GET.get('product'))
    request.user.can_view(product)

    product_data = json.loads(product.data)

    if 'store' in product_data:
        store = product_data['store']
    else:
        store = None

    tpl = 'shippement_info.html'
    if request.GET.get('for') == 'order':
        tpl = 'shippement_info_order.html'

    return render(request, tpl, {
        'country_code': country_code,
        'info': shippement_data,
        'store': store
    })


@login_required
def acp_users_list(request):
    if not request.user.is_superuser:
        raise PermissionDenied()

    if request.GET.get('cache') == '0':
        cache.delete_pattern('template.cache.acp_users.*')

    users = User.objects.select_related('profile', 'profile__plan').order_by('-date_joined')

    if request.GET.get('plan', None):
        users = users.filter(profile__plan_id=request.GET.get('plan'))


    plans = GroupPlan.objects.all()
    profiles = UserProfile.objects.all()

    return render(request, 'acp/users_list.html', {
        'users': users,
        'plans': plans,
        'profiles': profiles,
        'users_count': users.count(),
        'show_products': request.GET.get('products'),
        'page': 'acp_users_list',
        'breadcrumbs': ['ACP', 'Users List']
    })


@login_required
def acp_graph(request):
    if not request.user.is_superuser:
        raise PermissionDenied()

    products = ShopifyProduct.objects.all() \
        .extra({'created': 'date(%s.created_at)' % ShopifyProduct._meta.db_table}) \
        .values('created') \
        .annotate(created_count=Count('id')) \
        .order_by('-created')

    users = User.objects.all() \
        .extra({'created': 'date(%s.date_joined)' % User._meta.db_table}) \
        .values('created') \
        .annotate(created_count=Count('id')) \
        .order_by('-created')

    stores_count = ShopifyStore.objects.count()
    products_count = ShopifyProduct.objects.count()

    return render(request, 'acp/graph.html', {
        'products': products,
        'products_count': products_count,
        'users': users,
        'stores_count': stores_count,
        'page': 'acp_graph',
        'breadcrumbs': ['ACP', 'Graph Analytics']
    })


@login_required
def acp_groups(request):
    if not request.user.is_superuser and not request.user.has_perm('leadgalaxy.add_planregistration'):
        raise PermissionDenied()

    if request.method == 'POST':
        if request.POST.get('import'):
            data = json.loads(request.POST.get('import'))
            new_permissions = []
            info = ''
            for i in data:
                try:
                    AppPermission.objects.get(name=i['name'])
                except:
                    perm = AppPermission(name=i['name'], description=i['description'])
                    perm.save()

                    new_permissions.append(perm)
                    info = info + '%s: ' % perm.name

                    for p in i['plans']:
                        try:
                            plan = GroupPlan.objects.get(title=p['title'])
                        except:
                            continue
                        plan.permissions.add(perm)

                        info = info + '%s, ' % plan.title

                    info = info + '<br> '

            messages.success(request,
                             'Permission import success<br> new permissions: %d<br>%s' % (len(new_permissions), info))
        else:
            plan = GroupPlan.objects.get(id=request.POST['default-plan'])
            GroupPlan.objects.all().update(default_plan=0)
            plan.default_plan = 1
            plan.save()
    elif request.GET.get('perm-name'):
        name = request.GET.get('perm-name').strip()
        description = request.GET.get('perm-description').strip()
        perms = []

        if request.GET.get('perm-view'):
            perm = AppPermission(name='%s.view' % name, description='%s | View' % description)
            perm.save()

            perms.append(perm)

        if request.GET.get('perm-use'):
            perm = AppPermission(name='%s.use' % name, description='%s | Use' % description)
            perm.save()

            perms.append(perm)

        for i in request.GET.getlist('perm-grant-to'):
            plan = GroupPlan.objects.get(id=i)
            for p in perms:
                plan.permissions.add(p)

        messages.success(request, 'New permission added.')
        return HttpResponseRedirect('/acp/groups?add=1')

    elif request.GET.get('export'):
        data = []
        for i in AppPermission.objects.all():
            perm = {
                'name': i.name,
                'description': i.description,
                'plans': []
            }

            for p in i.groupplan_set.all():
                perm['plans'].append({
                    'id': p.id,
                    'title': p.title
                })

            data.append(perm)

        return JsonResponse(data, safe=False)

    if request.user.is_superuser:
        plans = GroupPlan.objects.all()
        tpl = 'acp/groups.html'
    else:
        plans = GroupPlan.objects.filter(id=8)
        tpl = 'acp/groups_limited.html'

    return render(request, tpl, {
        'plans': plans,
        'page': 'acp_groups',
        'breadcrumbs': ['ACP', 'Plans &amp; Groups']
    })


@login_required
def acp_groups_install(request):
    if not request.user.is_superuser:
        raise PermissionDenied()

    from django.db import transaction

    plan = GroupPlan.objects.get(id=request.GET.get('default'))
    vip_plan = GroupPlan.objects.get(id=request.GET.get('vip'))
    users = User.objects.filter(profile__plan=None)

    if (request.GET.get('confirm', 'no') != 'yes'):
        default_count = 0
        vip_count = 0
        for user in users:
            if 'VIP Members' in user.groups.all().values_list('name', flat=True):
                vip_count += 1
            else:
                default_count += 1

        return HttpResponse('Total: %d - Default: %d - VIP: %d' % (default_count + vip_count, default_count, vip_count))

    count = 0
    with transaction.atomic():
        for user in users:
            if 'VIP Members' in user.groups.all().values_list('name', flat=True):
                profile = UserProfile(user=user, plan=vip_plan)
            else:
                profile = UserProfile(user=user, plan=plan)

            profile.save()

            count += 1

    return HttpResponse('Done, changed: %d' % count)


def autocomplete(request, target):
    if not request.user.is_authenticated():
        return JsonResponse({'error': 'User login required'})

    q = request.GET.get('query', '')

    if target == 'types':
        types = []
        for product in request.user.models_user.shopifyproduct_set.all():
            prodct_info = json.loads(product.data)
            ptype = prodct_info.get('type')
            if ptype not in types:
                if q:
                    if q.lower() in ptype.lower():
                        types.append(ptype)
                else:
                    types.append(ptype)

        return JsonResponse({'query': q, 'suggestions': [{'value': i, 'data': i} for i in types]}, safe=False)

    elif target == 'tags':
        tags = []
        for product in request.user.models_user.shopifyproduct_set.all():
            prodct_info = json.loads(product.data)
            for i in prodct_info.get('tags', '').split(','):
                i = i.strip()
                if i and i not in tags:
                    if q:
                        if q.lower() in i.lower():
                            tags.append(i)
                    else:
                        tags.append(i)

        return JsonResponse({'query': q, 'suggestions': [{'value': j, 'data': j} for j in tags]}, safe=False)
    else:
        return JsonResponse({'error': 'Unknown target'})


@login_required
def upload_file_sign(request):
    import time
    import base64
    import hmac
    import urllib
    from hashlib import sha1

    if not request.user.can('image_uploader.use'):
        return JsonResponse({'error': 'You don\'t have access to this feature.'})

    AWS_ACCESS_KEY = os.environ.get('AWS_ACCESS_KEY_ID')
    AWS_SECRET_KEY = os.environ.get('AWS_SECRET_ACCESS_KEY')
    S3_BUCKET = os.environ.get('S3_BUCKET_NAME')

    object_name = urllib.quote_plus(request.GET.get('file_name'))
    mime_type = request.GET.get('file_type')

    if 'image' not in mime_type.lower():
        return JsonResponse({'error': 'None allowed file type'})

    expires = int(time.time() + 60 * 60 * 24)
    amz_headers = "x-amz-acl:public-read"

    string_to_sign = "PUT\n\n%s\n%d\n%s\n/%s/%s" % (mime_type, expires, amz_headers, S3_BUCKET, object_name)

    signature = base64.encodestring(hmac.new(AWS_SECRET_KEY.encode(), string_to_sign.encode('utf8'), sha1).digest())
    signature = urllib.quote_plus(signature.strip())

    url = 'https://%s.s3.amazonaws.com/%s' % (S3_BUCKET, object_name)

    content = {
        'signed_request': '%s?AWSAccessKeyId=%s&Expires=%s&Signature=%s' % (url, AWS_ACCESS_KEY, expires, signature),
        'url': url,
    }

    return JsonResponse(content, safe=False)


@login_required
def user_profile(request):
    profile = request.user.profile
    bundles = profile.bundles.all().values_list('register_hash', flat=True)
    extra_bundles = []

    if profile.plan.register_hash == '5427f85640fb78728ec7fd863db20e4c':  # JVZoo Pro Plan
        if 'b961a2a0f7101efa5c79b8ac80b75c47' not in bundles:  # JVZoo Elite Bundle
            extra_bundles.append({
                'title': 'Add Elite Bundle',
                'url': 'http://www.shopifiedapp.com/elite',
            })

        if '2fba7df0791f67b61581cfe37e0d7b7d' not in bundles:  # JVZoo Unlimited
            extra_bundles.append({
                'title': 'Add Unlimited Bundle',
                'url': 'http://www.shopifiedapp.com/unlimited',
            })

    bundles = profile.bundles.filter(hidden_from_user=False)

    return render(request, 'user/profile.html', {
        'countries': utils.get_countries(),
        'now': timezone.now(),
        'extra_bundles': extra_bundles,
        'bundles': bundles,
        'page': 'user_profile',
        'breadcrumbs': ['Profile']
    })


def upgrade_required(request):
    return render(request, 'upgrade.html')


def pixlr_serve_image(request):
    img_url = request.GET.get('image')
    allowed_domains = ['alicdn', 'amazonaws']

    if utils.get_domain(img_url) in allowed_domains:
        import mimetypes
        mimetype = mimetypes.guess_type(img_url)[0]
        allowed_mimetypes = ['image/jpeg', 'image/png', 'image/gif']

        if mimetype in allowed_mimetypes:
            import StringIO
            fp = StringIO.StringIO(requests.get(img_url).content)

            return HttpResponse(fp, content_type=mimetype)

    raise Http404("Image not found. %s" % img_url)


@login_required
def save_image_s3(request):
    """Saves the image in img_url into S3 with the name img_name"""
    import StringIO
    if 'advanced' in request.GET:
        # Pixlr
        if not request.user.can('advanced_photo_editor.use'):
            return render(request, 'upgrade.html')

        product_id = request.GET.get('product')
        image_id = request.GET.get('image_id')
        image = request.FILES.get('image')
        img_url = image.name

        json_response = False
        fp = StringIO.StringIO(image.read())
    else:
        # Aviary
        import urllib2
        if not request.user.can('aviary_photo_editor.use'):
            return render(request, 'upgrade.html')

        product_id = request.POST.get('product')
        img_url = request.POST.get('url')

        json_response = True
        fp = StringIO.StringIO(urllib2.urlopen(img_url).read())

    import boto
    from boto.s3.key import Key

    AWS_ACCESS_KEY = os.environ.get('AWS_ACCESS_KEY_ID')
    AWS_SECRET_KEY = os.environ.get('AWS_SECRET_ACCESS_KEY')
    S3_BUCKET = os.environ.get('S3_BUCKET_NAME')

    img_name = 'uploads/u%d/%s' % (request.user.id, img_url.split('/')[-1])

    product = ShopifyProduct.objects.get(user=request.user, id=product_id)

    conn = boto.connect_s3(AWS_ACCESS_KEY, AWS_SECRET_KEY)
    bucket = conn.get_bucket(S3_BUCKET)
    k = Key(bucket)
    k.key = img_name

    import mimetypes
    mimetype = mimetypes.guess_type(img_url)[0]
    k.set_metadata("Content-Type", mimetype)
    k.set_contents_from_file(fp)
    k.make_public()

    upload_url = 'http://%s.s3.amazonaws.com/%s' % (S3_BUCKET, img_name)

    upload = UserUpload(user=request.user.models_user, product=product, url=upload_url)
    upload.save()

    pixlr_key = 'pixlr_%s' % request.GET.get('key')
    pixlr_data = cache.get(pixlr_key)
    pixlr_data['url'] = upload_url
    pixlr_data['status'] = 'changed'
    cache.set(pixlr_key, pixlr_data, timeout=600) # 10 minutes timeout

    return JsonResponse({
        'status': 'ok',
        'url': upload_url
    })


@login_required
def orders_view(request):
    if not request.user.can('orders.use'):
        return render(request, 'upgrade.html')

    stores = []
    all_orders = []
    store = None
    post_per_page = utils.safeInt(request.GET.get('ppp'), 20)
    page = utils.safeInt(request.GET.get('page'), 1)

    if request.GET.get('store'):
        store = ShopifyStore.objects.get(id=request.GET.get('store'))
        request.session['last_store'] = store.id
    else:
        if 'last_store' in request.session:
            store = ShopifyStore.objects.get(id=request.session['last_store'])
        else:
            stores = request.user.profile.get_active_stores()
            if len(stores):
                store = stores[0]

        if not store:
            messages.warning(request, 'Please add at least one store before using the Orders page.')
            return HttpResponseRedirect('/')

    request.user.can_view(store)

    models_user = request.user.models_user

    sort = utils.get_orders_filter(request, 'sort', 'desc')
    status = utils.get_orders_filter(request, 'status', 'open')
    fulfillment = utils.get_orders_filter(request, 'fulfillment', 'unshipped')
    financial = utils.get_orders_filter(request, 'financial', 'paid')
    sort_field = utils.get_orders_filter(request, 'sort', 'created_at')
    sort_type = utils.get_orders_filter(request, 'desc')

    query = request.GET.get('query')
    query_order = request.GET.get('query_order')
    query_customer = request.GET.get('query_customer')
    query_address = request.GET.get('query_address')

    if request.GET.get('old') == '1':
        shopify_orders_utils.disable_store_sync(store)
    elif request.GET.get('old') == '0':
        shopify_orders_utils.enable_store_sync(store)

    store_order_synced = shopify_orders_utils.is_store_synced(store)
    store_sync_enabled = store_order_synced and shopify_orders_utils.is_store_sync_enabled(store)

    if not store_sync_enabled:
        open_orders = store.get_orders_count(status, fulfillment, financial)
        orders = xrange(0, open_orders)

        paginator = utils.ShopifyOrderPaginator(orders, post_per_page)
        paginator.set_store(store)
        paginator.set_order_limit(post_per_page)
        paginator.set_filter(status, fulfillment, financial)
        paginator.set_reverse_order(sort == 'desc')
        paginator.set_query(utils.safeInt(query, query))

        page = min(max(1, page), paginator.num_pages)
        current_page = paginator.page(page)
        page = current_page
    else:
        orders = ShopifyOrder.objects.filter(user=request.user.models_user, store=store)

        if query_order:
            try:
                order_number = re.findall('[0-9]+', query_order)
                order_number = int(order_number[0])
            except:
                order_number = 0

            if order_number:
                orders = orders.filter(Q(order_number=order_number) |
                                       Q(order_number=(order_number-1000)) |
                                       Q(order_id=order_number))
            else:
                orders = orders.filter(Q(order_id=utils.safeInt(query_order)))

        if query_customer:
            orders = orders.filter(Q(customer_id=utils.safeInt(query_customer, -1)) |
                                   Q(customer_name__icontains=query_customer) |
                                   Q(customer_email__iexact=query_customer))

        if query_address:
            orders = orders.filter(Q(country_code__iexact=query_address))

        query = None

        if status == 'open':
            orders = orders.filter(closed_at=None, cancelled_at=None)
        elif status == 'closed':
            orders = orders.exclude(closed_at=None)
        elif status == 'cancelled':
            orders = orders.exclude(cancelled_at=None)

        if fulfillment == 'unshipped':
            orders = orders.filter(fulfillment_status=None)
        elif fulfillment == 'shipped':
            orders = orders.filter(fulfillment_status='fulfilled')
        elif fulfillment == 'partial':
            orders = orders.filter(fulfillment_status='partial')

        if financial != 'any':
            orders = orders.filter(financial_status=financial)

        if request.GET.get('connected') == 'true':
            orders = orders.exclude(shopifyorderline__product=None)

        if sort_field in ['created_at', 'updated_at', 'total_price', 'country_code']:
            sort_desc = '-' if sort_type == 'true' else ''
            orders = orders.order_by(sort_desc + sort_field)

        paginator = utils.SimplePaginator(orders, post_per_page)
        page = min(max(1, page), paginator.num_pages)
        current_page = paginator.page(page)
        page = current_page

        open_orders = paginator.count

        if open_orders:
            rep = requests.get(
                url=store.get_link('/admin/orders.json', api=True),
                params={
                    'ids': ','.join([str(i.order_id) for i in page]),
                    'status': 'any',
                    'fulfillment_status': 'any',
                    'financial_status': 'any',
                }
            )

            page = shopify_orders_utils.sort_orders(rep.json()['orders'], page)
        else:
            page = []

    products_cache = {}
    auto_orders = request.user.can('auto_order.use')
    uk_provinces = None

    orders_ids = []
    products_ids = []
    for order in page:
        orders_ids.append(order['id'])
        for line in order['line_items']:
            line_id = line.get('product_id')
            products_ids.append(line_id)

    orders_list = {}
    res = ShopifyOrderTrack.objects.filter(user=models_user, order_id__in=orders_ids)
    for i in res:
        orders_list['{}-{}'.format(i.order_id, i.line_id)] = i

    images_list = {}
    res = ShopifyProductImage.objects.filter(store=store, product__in=products_ids)
    for i in res:
        images_list['{}-{}'.format(i.product, i.variant)] = i.image

    disable_affiliate = models_user.get_config('_disable_affiliate', False)
    api_key, tracking_id = utils.get_user_affiliate(models_user)

    for index, order in enumerate(page):
        order['date_str'] = arrow.get(order['created_at']).format('MM/DD/YYYY')
        order['date_tooltip'] = arrow.get(order['created_at']).format('YYYY-MM-DD HH:mm:ss ZZ')
        order['order_url'] = store.get_link('/admin/orders/%d' % order['id'])
        order['store'] = store
        order['placed_orders'] = 0
        order['connected_lines'] = 0
        order['lines_count'] = len(order['line_items'])

        for i, el in enumerate((order['line_items'])):
            var_link = store.get_link('/admin/products/{}/variants/{}'.format(el['product_id'],
                                                                              el['variant_id']))
            order['line_items'][i]['variant_link'] = var_link

            order['line_items'][i]['image'] = {
                'store': store.id,
                'product': el['product_id'],
                'variant': el['variant_id']
            }

            order['line_items'][i]['image_src'] = images_list.get('{}-{}'.format(el['product_id'], el['variant_id']))

            shopify_order = orders_list.get('{}-{}'.format(order['id'], el['id']))
            order['line_items'][i]['shopify_order'] = shopify_order

            if shopify_order:
                order['placed_orders'] += 1

            if el['product_id'] in products_cache:
                product = products_cache[el['product_id']]
            else:
                product = ShopifyProduct.objects.filter(user=models_user, shopify_export__shopify_id=el['product_id']).first()

            if product:
                original_info = product.get_original_info()
                if not original_info:
                    original_info = {}

                order['line_items'][i]['product'] = product
                order['line_items'][i]['domain'] = original_info.get('domain')
                order['connected_lines'] += 1

                original_url = original_info.get('url')
                if utils.get_domain(original_url) == 'aliexpress':
                    try:
                        original_id = re.findall('[/_]([0-9]+).html', original_url)[0]
                        order['line_items'][i]['original_url'] = 'http://www.aliexpress.com/item//{}.html'.format(
                            original_id)

                        order['line_items'][i]['original_id'] = original_id
                    except:
                        order['line_items'][i]['original_url'] = original_url
                        print 'WARNING: ID not found for:', original_url
                else:
                    order['line_items'][i]['original_url'] = original_url

            products_cache[el['product_id']] = product

            if auto_orders and 'shipping_address' in order:
                try:
                    shipping_address_asci = {}  # Aliexpress doesn't allow unicode
                    shipping_address = order['shipping_address']
                    for k in shipping_address.keys():
                        if shipping_address[k] and type(shipping_address[k]) is unicode:
                            shipping_address_asci[k] = unidecode(shipping_address[k])
                        else:
                            shipping_address_asci[k] = shipping_address[k]

                    if not shipping_address_asci[u'province']:
                        if shipping_address_asci[u'country'] == u'United Kingdom':
                            if not uk_provinces:
                                uk_provinces = load_uk_provincess()

                            province = uk_provinces.get(shipping_address_asci[u'city'].lower().strip(), u'')
                            if not province:
                                print 'WARNING: UK Province not found for:', shipping_address_asci[u'city']

                            shipping_address_asci[u'province'] = province
                        else:
                            shipping_address_asci[u'province'] = shipping_address_asci[u'country_code']
                    elif shipping_address_asci[u'province'] == 'Washington DC':
                        shipping_address_asci[u'province'] = u'Washington'

                    phone = shipping_address_asci.get('phone')
                    if not phone or models_user.get_config('order_default_phone') != 'customer':
                        phone = models_user.get_config('order_phone_number')

                    order_data = {
                        'id': '{}_{}_{}'.format(store.id, order['id'], el['id']),
                        'variant': el['variant_title'],
                        'quantity': el['fulfillable_quantity'],
                        'shipping_address': shipping_address_asci,
                        'order_id': order['id'],
                        'line_id': el['id'],
                        'store': store.id,
                        'order': {
                            'phone': phone,
                            'note': models_user.get_config('order_custom_note'),
                            'epacket': bool(models_user.get_config('epacket_shipping')),
                            'auto_mark': bool(models_user.get_config('auto_ordered_mark')),  # Auto mark as Ordered
                        }
                    }

                    if product:
                        order_data['product_id'] = product.id

                        try:
                            variants_map = json.loads(product.variants_map)
                        except:
                            variants_map = {}

                        mapped = variants_map.get(str(el['variant_id']))
                        if mapped:
                            order_data['variant'] = ' / '.join(mapped.split(','))

                    if order['line_items'][i]['domain'] == 'aliexpress':
                        if cache.set('order_%s' % order_data['id'], order_data, timeout=3600):
                            order['line_items'][i]['order_data_id'] = order_data['id']

                        order['line_items'][i]['order_data'] = order_data
                except:
                    pass

        all_orders.append(order)

    if store_order_synced:
        countries = utils.get_countries()
    else:
        countries = []

    return render(request, 'orders_new.html', {
        'orders': all_orders,
        'store': store,
        'paginator': paginator,
        'current_page': current_page,
        'open_orders': open_orders,
        'sort': sort_field,
        'sort_type': sort_type,
        'status': status,
        'financial': financial,
        'fulfillment': fulfillment,
        'query': query,
        'aliexpress_affiliate': (api_key and tracking_id and not disable_affiliate),
        'store_order_synced': store_order_synced,
        'store_sync_enabled': store_sync_enabled,
        'countries': countries,
        'page': 'orders',
        'breadcrumbs': ['Orders']
    })


@login_required
def orders_track(request):
    if not request.user.can('orders.use'):
        return render(request, 'upgrade.html')

    order_map = {
        'order': 'order_id',
        'source': 'source_id',
        'status': 'source_status',
        'tracking': 'source_tracking',
        'add': 'created_at',
        'update': 'status_updated_at',
    }

    for k, v in order_map.items():
        order_map['-' + k] = '-' + v

    sorting = request.GET.get('sort', '-update')
    sorting = order_map.get(sorting, 'status_updated_at')

    store = None
    post_per_page = utils.safeInt(request.GET.get('ppp'), 20)
    page = utils.safeInt(request.GET.get('page'), 1)
    query = request.GET.get('query')
    tracking_filter = request.GET.get('tracking')
    fulfillment_filter = request.GET.get('fulfillment')
    hidden_filter = request.GET.get('hidden')

    if request.GET.get('store'):
        store = ShopifyStore.objects.get(id=request.GET.get('store'))
        request.session['last_store'] = store.id
    else:
        if 'last_store' in request.session:
            store = ShopifyStore.objects.get(id=request.session['last_store'])
        else:
            stores = request.user.profile.get_active_stores()
            if len(stores):
                store = stores[0]

        if not store:
            messages.warning(request, 'Please add at least one store before using the Orders page.')
            return HttpResponseRedirect('/')

    request.user.can_view(store)

    orders = ShopifyOrderTrack.objects.select_related('store').filter(user=request.user.models_user, store=store)

    if query:
        order_id = shopify_orders_utils.order_id_from_number(store, query)

        if order_id:
            query = str(order_id)

        orders = orders.filter(Q(order_id=utils.clean_query_id(query)) |
                               Q(source_id=utils.clean_query_id(query)) |
                               Q(source_tracking=query))

    if tracking_filter == '0':
        orders = orders.filter(source_tracking='')
    elif tracking_filter == '1':
        orders = orders.exclude(source_tracking='')

    if fulfillment_filter == '1':
        orders = orders.filter(shopify_status='fulfilled')
    elif fulfillment_filter == '0':
        orders = orders.exclude(shopify_status='fulfilled')

    if hidden_filter == '1':
        orders = orders.filter(hidden=True)
    elif not hidden_filter or hidden_filter == '0':
        orders = orders.exclude(hidden=True)

    orders = orders.order_by(sorting)

    paginator = utils.SimplePaginator(orders, post_per_page)
    page = min(max(1, page), paginator.num_pages)
    page = paginator.page(page)
    orders = page.object_list

    if len(orders):
        orders = utils.get_tracking_orders(store, orders)

    ShopifyOrderTrack.objects.filter(user=request.user.models_user,
                                id__in=[i.id for i in orders]) \
                        .update(seen=True)

    return render(request, 'orders_track.html', {
        'store': store,
        'orders': orders,
        'paginator': paginator,
        'current_page': page,
        'page': 'orders_track',
        'breadcrumbs': [{'title': 'Orders', 'url': '/orders'}, 'Tracking']
    })


@login_required
def orders_place(request):
    try:
        product = request.GET['product']
        data = request.GET['SAPlaceOrder']
    except:
        raise Http404("Product or Order not set")

    # Check for Aliexpress Affiliate Program
    api_key, tracking_id = utils.get_user_affiliate(request.user.models_user)

    disable_affiliate = request.user.get_config('_disable_affiliate', False)

    redirect_url = None
    if not disable_affiliate and api_key and tracking_id:
        affiliate_link = utils.get_aliexpress_promotion_links(api_key, tracking_id, product)

        if affiliate_link:
            redirect_url = '{}&SAPlaceOrder={}'.format(affiliate_link, data)

    if not redirect_url:
        redirect_url = '{}?SAPlaceOrder={}'.format(product, data)

    for k in request.GET.keys():
        if k.startswith('SA') and k not in redirect_url:
            redirect_url = '{}&{}={}'.format(redirect_url, k, request.GET[k])

    return HttpResponseRedirect(redirect_url)


@login_required
def products_update(request):
    if not request.user.can('price_changes.use'):
        return render(request, 'upgrade.html')

    show_hidden = 'hidden' in request.GET

    product = request.GET.get('product')
    if product:
        product = get_object_or_404(ShopifyProduct, id=product)
        request.user.can_view(product)

    post_per_page = utils.safeInt(request.GET.get('ppp'), 20)
    page = utils.safeInt(request.GET.get('page'), 1)

    changes = AliexpressProductChange.objects.select_related('product') \
                                     .select_related('product__shopify_export') \
                                     .filter(user=request.user.models_user)

    if product:
        changes = changes.filter(product=product)
    else:
        changes = changes.filter(hidden=show_hidden)

    changes = changes.order_by('-updated_at')

    paginator = utils.SimplePaginator(changes, post_per_page)
    page = min(max(1, page), paginator.num_pages)
    page = paginator.page(page)
    changes = page.object_list

    product_changes = []
    for i in changes:
        change = {'qelem': i}
        change['id'] = i.id
        change['data'] = json.loads(i.data)
        change['changes'] = utils.product_changes_remap(change['data'])
        change['product'] = i.product
        change['shopify_link'] = i.product.shopify_link()
        change['original_link'] = i.product.get_original_info().get('url')

        product_changes.append(change)

    if not show_hidden:
        AliexpressProductChange.objects.filter(user=request.user.models_user,
                                               id__in=[i['id'] for i in product_changes]) \
                                       .update(seen=True)

    # Allow sending notification for new changes
    request.user.set_config('_product_change_notify', False)

    tpl = 'product_alerts.html' if product else 'products_update.html'

    # Delete sidebar alert info cache
    from django.core.cache.utils import make_template_fragment_key
    cache.delete(make_template_fragment_key('alert_info', [request.user.id]))

    return render(request, tpl, {
        'product_changes': product_changes,
        'show_hidden': show_hidden,
        'product': product,
        'paginator': paginator,
        'current_page': page,
        'page': 'products_update',
        'breadcrumbs': [{'title': 'Products', 'url': '/product'}, 'Alerts']
    })


@login_required
def bundles_bonus(request, bundle_id):
    bundle = get_object_or_404(FeatureBundle, register_hash=bundle_id)
    if request.method == 'POST':
        form = EmailForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data['email']
            reg = utils.generate_plan_registration(plan=None, bundle=bundle, data={'email': email})

            try:
                user = User.objects.get(email__iexact=email)
                user.profile.bundles.add(bundle)

                reg.expired = True
            except User.DoesNotExist:
                user = None

            reg.save()

            messages.success(request, 'Bundle %s has been added to your account.' % bundle.title)
            return HttpResponseRedirect('/')

    else:
        initial = {}

        if request.user.is_authenticated():
            initial = {'email': request.user.email}

        form = RegisterForm(initial=initial)

    return render(request, "bundles_bonus.html", {
        'form': form,
        'bundle': bundle
    })


@login_required
def product_feeds(request):
    return render(request, 'product_feeds.html', {
        'page': 'product_feeds',
        'breadcrumbs': ['Marketing', 'Product Feeds']
    })


@login_required
def products_collections(request, collection):
    post_per_page = request.GET.get('ppp', 25)
    page = request.GET.get('page', 1)
    page = max(1, page)

    paginator = utils.ProductsCollectionPaginator([], post_per_page)
    paginator.set_product_per_page(post_per_page)
    paginator.set_current_page(page)
    paginator.set_query(request.GET.get('title'))

    extra_filter = {}
    filter_map = {
        'price_min': 'price_min',
        'price_max': 'price_max',
        'type': 'category',
        'sort': 'order'
    }

    for k, v in filter_map.items():
        if request.GET.get(k):
            extra_filter[v] = request.GET.get(k)

    paginator.set_extra_filter(extra_filter)

    page = paginator.page(page)

    return render(request, 'products_collections.html', {
        'products': page.object_list,
        'paginator': paginator,
        'current_page': page,

        'page': 'products_collections',
        'breadcrumbs': ['Products', 'Collections', 'US']
    })


@login_required
def subusers(request):
    if not request.user.can('sub_users.use'):
        return render(request, 'upgrade.html')

    if request.user.is_subuser:
        raise PermissionDenied()

    sub_users = User.objects.filter(profile__subuser_parent=request.user)

    return render(request, 'subusers_manage.html', {
        'sub_users': sub_users,
        'page': 'subusers',
        'breadcrumbs': ['Account', 'Sub Users']
    })


@login_required
def subusers_perms(request, user_id):
    try:
        user = User.objects.get(id=user_id, profile__subuser_parent=request.user)
    except User.DoesNotExist:
        return JsonResponse({'error': 'User not found'}, status=404)
    except:
        return JsonResponse({'error': 'Unknown Error'}, status=500)

    if request.method == 'POST':
        form = SubUserStoresForm(request.POST,
                                 instance=user.profile,
                                 parent_user=request.user)
        if form.is_valid():
            form.save()

            messages.success(request, 'User permissions has been updated')
        else:
            messages.error(request, 'Error occurred during user permissions update')

        return HttpResponseRedirect(reverse('subusers'))

    else:
        form = SubUserStoresForm(instance=user.profile,
                                 parent_user=request.user)

    return render(request, 'subusers_perms.html', {
        'subuser': user,
        'form': form,
        'page': 'subusers',
        'breadcrumbs': ['Account', 'Sub Users']
    })

@login_required
def acp_users_emails(request):
    # TODO: Move to top
    if not request.user.is_superuser:
        return HttpResponseRedirect('/')

    res = ShopifyProduct.objects.exclude(shopify_export__isnull=True)
    users = []
    filtred = []
    for row in res:
        if row.user not in users and row.user not in filtred and 'VIP' not in row.user.profile.plan.title:
            users.append(row.user)
        else:
            filtred.append(row.user)

    o = ''
    for i in users:
        o = '{}{}<br>\n'.format(o, i.email)

    return HttpResponse(o)


def get_product_feed(request, store_id, revision=1):
    try:
        assert len(store_id) == 8
        store = ShopifyStore.objects.get(store_hash__startswith=store_id)
    except (AssertionError, ShopifyStore.DoesNotExist):
        raise Http404('Feed not found')

    feed = utils.ProductFeed(store, revision)
    feed.init()

    for p in utils.get_shopify_products(store, all_products=True):
        feed.add_product(p)

    if request.GET.get('stream') == '1':
        from django.http import StreamingHttpResponse

        return StreamingHttpResponse(feed.get_feed(), content_type='application/xml')
    else:
        return HttpResponse(feed.get_feed(), content_type='application/xml')


@login_required
def logout(request):
    user_logout(request)
    return redirect('/')


def register(request, registration=None):
    if request.user.is_authenticated():
        messages.warning(request, 'You are already logged in')
        return HttpResponseRedirect('/')

    if registration:
        # Convert the hash to a PlanRegistration model
        registration = get_object_or_404(PlanRegistration, register_hash=registration)

        if registration.expired:
            raise Http404('Registration link expired')

    if request.method == 'POST':
        form = RegisterForm(request.POST)
        form.set_plan_registration(registration)

        if form.is_valid():
            new_user = form.save()
            utils.create_new_profile(new_user)

            if registration is None or registration.get_usage_count() is None:
                utils.apply_plan_registrations(form.cleaned_data['email'])
            else:
                utils.apply_shared_registration(new_user, registration)

            messages.info(request, "Thanks for registering. You are now logged in.")
            new_user = authenticate(username=form.cleaned_data['username'],
                                    password=form.cleaned_data['password1'])

            login(request, new_user)

            return HttpResponseRedirect("/")
    else:
        try:
            initial = {
                'email': registration.email,
            }
        except:
            initial = {}

        form = RegisterForm(initial=initial)

    if registration and registration.email:
        form.fields['email'].widget.attrs['readonly'] = True

    return render(request, "registration/register.html", {
        'form': form,
        'registration': registration
    })


def crossdomain(request):
    html = """
        <cross-domain-policy>
            <allow-access-from domain="*.pixlr.com"/>
            <site-control permitted-cross-domain-policies="master-only"/>
            <allow-http-request-headers-from domain="*.pixlr.com" headers="*" secure="true"/>
        </cross-domain-policy>
    """
    return HttpResponse(html, content_type='application/xml')


def robots_txt(request):
    return HttpResponse("User-agent: *\nDisallow: /\n", content_type='text/plain')


def handler404(request):
    response = render_to_response('404.html', {},
                                  context_instance=RequestContext(request))
    response.status_code = 404
    return response


def handler500(request):
    response = render_to_response('500.html', {},
                                  context_instance=RequestContext(request))
    response.status_code = 500
    return response
