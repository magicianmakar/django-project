from django.shortcuts import render, get_object_or_404, render_to_response
from django.http import HttpResponse, HttpResponseRedirect, Http404
from django.contrib.auth.decorators import login_required
from django.contrib.auth import logout as user_logout
from django.shortcuts import redirect
from django.template import Context, Template, RequestContext
from django.contrib.auth.models import User
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db.models import Count, F
from django.contrib.auth import authenticate, login
from django.http import JsonResponse
from django.core.paginator import Paginator
from django.core.urlresolvers import reverse
from django.core.mail import send_mail
from django.utils import timezone

from unidecode import unidecode

from app import settings

from .models import *
from .forms import *

import os
import re
import json
import requests
import arrow
import traceback

import utils
from province_helper import load_uk_provincess


@login_required
def index_view(request):
    stores = request.user.shopifystore_set.filter(is_active=True)
    config = request.user.profile.get_config()

    return render(request, 'index.html', {
        'stores': stores,
        'config': config,
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
        return JsonResponse({'error': 'Unknown method: {}'.format(method)})

    if 'access_token' in data:
        token = data.get('access_token')
        user = utils.get_user_from_token(token)
    else:
        if request.user.is_authenticated:
            user = request.user
        else:
            user = None

    if target not in ['login', 'shopify', 'shopify-update', 'save-for-later'] and not user:
        return JsonResponse({'error': 'Unauthenticated api call.'})

    if target == 'login':
        username = data.get('username')
        password = data.get('password')

        if '@' in username:
            try:
                username = User.objects.get(email=username).username
            except:
                return JsonResponse({'error': 'Unvalide email or password'})

        user = authenticate(username=username, password=password)
        if user is not None:
            if user.is_active:
                token = utils.get_access_token(user)

                return JsonResponse({
                    'token': token,
                    'user': {
                        'groups': [str(i) for i in user.groups.all().values_list('name', flat=True)],
                        'username': user.username,
                        'email': user.email
                    }
                }, safe=False)

        return JsonResponse({'error': 'Unvalide username or password'})

    if method == 'POST' and target == 'register':
        form = RegisterForm(request.POST)
        if form.is_valid():
            new_user = form.save()
            utils.create_new_profile(new_user)

            user = authenticate(username=form.cleaned_data['username'], password=form.cleaned_data['password1'])
            if user is not None:
                if user.is_active:
                    token = utils.get_access_token(user)
                    return JsonResponse({'token': token})
        else:
            return JsonResponse({'error': 'Unvalid form'})

    if method == 'GET' and target == 'stores':
        stores = []
        for i in user.shopifystore_set.filter(is_active=True):
            stores.append({
                'id': i.id,
                'name': i.title,
                'url': i.api_url
            })

        return JsonResponse(stores, safe=False)

    if method == 'POST' and target == 'add-store':
        name = data.get('name')
        url = data.get('url')

        total_stores = user.profile.plan.stores  # -1 mean unlimited
        user_saved_stores = user.shopifystore_set.filter(is_active=True).count()

        if (total_stores > -1) and (user_saved_stores + 1 > total_stores):
            return JsonResponse({
                'error': 'Your current plan allow up to %d linked stores, currently you have %d linked stores.' \
                         % (total_stores, user_saved_stores)
            })

        store = ShopifyStore(title=name, api_url=url, user=user)
        store.save()

        utils.attach_webhooks(store)

        stores = []
        for i in user.shopifystore_set.filter(is_active=True):
            stores.append({
                'name': i.title,
                'url': i.api_url
            })

        return JsonResponse(stores, safe=False)

    if method == 'POST' and target == 'delete-store':
        store_id = data.get('store')
        move_to = data.get('move-to')

        move_to_store = ShopifyStore.objects.get(id=move_to, user=user)
        ShopifyStore.objects.filter(id=store_id, user=user).update(is_active=False)
        ShopifyStore.objects.get(id=store_id, user=user).shopifyproduct_set.update(store=move_to_store)

        utils.detach_webhooks(ShopifyStore.objects.get(id=store_id, user=user))

        stores = []
        for i in user.shopifystore_set.filter(is_active=True):
            stores.append({
                'id': i.id,
                'name': i.title,
                'url': i.api_url
            })

        return JsonResponse(stores, safe=False)

    if method == 'POST' and target == 'update-store':
        store = ShopifyStore.objects.get(id=data.get('store'), user=user)

        attach = False
        if store.api_url != data.get('url'):
            utils.detach_webhooks(store)
            attach = True

        store.title = data.get('title')
        store.api_url = data.get('url')
        store.save()

        if attach:
            utils.attach_webhooks(store)

        return JsonResponse({'status': 'ok'})

    if method == 'GET' and target == 'product':
        try:
            product = ShopifyProduct.objects.get(id=data.get('product'), user=user)
        except:
            return JsonResponse({'error': 'Product not found'})

        return JsonResponse(json.loads(product.data), safe=False)

    if method == 'POST' and target == 'products-info':
        products = {}
        for p in data.getlist('products[]'):
            try:
                product = ShopifyProduct.objects.get(id=p, user=user)
                products[p] = json.loads(product.data)
            except:
                return JsonResponse({'error': 'Product not found'})

        return JsonResponse(products, safe=False)

    if method == 'POST' and (target == 'shopify' or target == 'shopify-update' or target == 'save-for-later'):
        req_data = json.loads(request.body)
        store = req_data['store']

        data = req_data['data']
        original_data = req_data.get('original', '')

        if 'access_token' in req_data:
            token = req_data['access_token']
            user = utils.get_user_from_token(token)

            if not user:
                return JsonResponse({'error': 'Unvalide access token: %s' % (token)})
        else:
            if request.user.is_authenticated:
                user = request.user
            else:
                return JsonResponse({'error': 'Unauthenticated user'})

        try:
            store = ShopifyStore.objects.get(id=store, user=user)
        except:
            return JsonResponse({
                'error': 'Selected store (%s) not found for user: %s' % (store, user.username if user else 'None')
            })

        original_url = json.loads(data).get('original_url', '')

        print 'original_url', original_url
        if 'amazon.com/' in original_url.lower() and not user.can('amazon_import.use') or \
           'sammydress.com/' in original_url.lower() and not user.can('sammydress_import.use') or \
           'ebay.com/' in original_url.lower() and not user.can('ebay_import.use'):

            return JsonResponse({
                'error': 'Importing from this store is not included in your current plan.'
            })

        endpoint = store.get_link('/admin/products.json', api=True)

        product_data = {}
        if target == 'shopify' or target == 'shopify-update':
            try:
                if target == 'shopify-update':
                    product = ShopifyProduct.objects.get(id=req_data['product'], user=user)
                    api_data = json.loads(data)
                    api_data['product']['id'] = product.get_shopify_id()

                    update_endpoint = store.get_link('/admin/products/{}.json'.format(product.get_shopify_id()), api=True)
                    r = requests.put(update_endpoint, json=api_data)
                else:
                    r = requests.post(endpoint, json=json.loads(data))
                    product_to_map = r.json()['product']

                    try:
                        # Link images with variants
                        mapped = utils.shopify_link_images(store, product_to_map)
                        if mapped:
                            r = mapped
                    except Exception as e:
                        traceback.print_exc()

                product_data = r.json()['product']
            except:
                traceback.print_exc()
                print '-----'
                try:
                    print r.text
                    print '-----'
                except:
                    pass

                try:
                    d = r.json()
                    return JsonResponse({'error': '[Shopify API Error] ' + ' | '.join(
                                        [k + ': ' + ''.join(d['errors'][k]) for k in d['errors']])})
                except:
                    return JsonResponse({'error': 'Shopify API Error'})

            pid = r.json()['product']['id']
            url = store.get_link('/admin/products/{}'.format(pid))

            if target == 'shopify':
                if 'product' in req_data:
                    try:
                        product = ShopifyProduct.objects.get(id=req_data['product'], user=user)

                        original_info = product.get_original_info()
                        if original_info:
                            original_url = original_info.get('url', '')
                    except Exception as e:
                        return JsonResponse({'error': 'Selected product not found ({})'.format(repr(e))})

                    product.shopify_id = pid
                    product.stat = 1
                    product.save()
                else:
                    product = None

                product_export = ShopifyProductExport(original_url=original_url, shopify_id=pid, store=store)
                product_export.save()

                if product:
                    product.shopify_export = product_export
                    product.save()
            else:
                messages.success(request, 'Product updated in Shopify.')

        elif target == 'save-for-later':  # save for later
            if 'product' in req_data:
                # Saved product update
                try:
                    product = ShopifyProduct.objects.get(id=req_data['product'], user=user)
                except:
                    return JsonResponse({'error': 'Selected product not found.'})

                product.store = store
                product.data = data
                product.stat = 0

            else:  # New product to save

                # Check if the user plan allow more product saving
                total_products = user.profile.plan.products  # -1 mean unlimited
                user_saved_products = user.shopifyproduct_set.count()

                if (total_products > -1) and (user_saved_products + 1 > total_products):
                    return JsonResponse({
                        'error': 'Your current plan allow up to %d saved products, currently you have %d saved products.' \
                                 % (total_products, user_saved_products)
                    })

                is_active = req_data.get('activate', True)

                product = ShopifyProduct(store=store, user=user, data=data, original_data=original_data, stat=0,
                                         is_active=is_active)
                product.notes = req_data.get('notes', '')

            product.save()

            utils.smart_board_by_product(user, product)

            url = request.build_absolute_uri('/product/%d' % product.id)
            pid = product.id
        else:
            return JsonResponse({'error': 'Unknown target {}'.format(target)})

        return JsonResponse({
            'product': {
                'url': url,
                'id': pid,
                'data': product_data
            }
        }, safe=False)

    if method == 'POST' and target == 'product-stat':
        try:
            product = ShopifyProduct.objects.get(id=data.get('product'), user=user)
        except:
            return JsonResponse({'error': 'Selected product not found.'})

        product.stat = data.get('sent')
        product.save()

        return JsonResponse({'status': 'ok'})

    if method == 'POST' and target == 'product-delete':
        product = ShopifyProduct.objects.get(id=data.get('product'), user=user)
        product.userupload_set.update(product=None)

        product.delete()

        return JsonResponse({'status': 'ok'})

    if method == 'POST' and target == 'bulk-edit':
        for p in data.getlist('product'):
            product = ShopifyProduct.objects.get(id=p, user=user)
            product_data = json.loads(product.data)

            product_data['title'] = data.get('title[%s]' % p)
            product_data['tags'] = data.get('tags[%s]' % p)
            product_data['price'] = utils.safeFloat(data.get('price[%s]' % p))
            product_data['compare_at_price'] = utils.safeFloat(data.get('compare_at[%s]' % p))
            product_data['type'] = data.get('type[%s]' % p)
            product_data['weight'] = data.get('weight[%s]' % p)
            # send_to_shopify = data.get('send_to_shopify[%s]'%p)

            product.data = json.dumps(product_data)
            product.save()

        return JsonResponse({'status': 'ok'})
    if method == 'POST' and target == 'product-edit':
        products = []
        for p in data.getlist('products[]'):
            product = ShopifyProduct.objects.get(id=p, user=user)
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
        total_boards = user.profile.plan.boards  # -1 mean unlimited
        user_saved_boards = user.shopifyboard_set.count()

        if (total_boards > -1) and (user_saved_boards + 1 > total_boards):
            return JsonResponse({
                'error': 'Your current plan allow up to %d boards, currently you have %d boards.' \
                         % (total_boards, user_saved_boards)
            })

        board = ShopifyBoard(title=data.get('title').strip(), user=user)
        board.save()

        return JsonResponse({
            'status': 'ok',
            'board': {
                'id': board.id,
                'title': board.title
            }
        })

    if method == 'POST' and target == 'board-add-products':
        board = ShopifyBoard.objects.get(user=user, id=data.get('board'))
        products = []
        for p in data.getlist('products[]'):
            product = ShopifyProduct.objects.get(id=p, user=user)
            # product.shopifyboard_set.clear()
            board.products.add(product)

        board.save()

        return JsonResponse({'status': 'ok'})

    if method == 'POST' and target == 'product-remove-board':
        board = ShopifyBoard.objects.get(user=user, id=data.get('board'))
        products = []
        for p in data.getlist('products[]'):
            product = ShopifyProduct.objects.get(id=p, user=user)
            # product.shopifyboard_set.clear()
            board.products.remove(product)

        board.save()

        return JsonResponse({'status': 'ok'})

    if method == 'POST' and target == 'product-board':
        product = ShopifyProduct.objects.get(id=data.get('product'), user=user)

        if data.get('board') == '0':
            product.shopifyboard_set.clear()
            product.save()

            return JsonResponse({
                'status': 'ok'
            })
        else:
            board = ShopifyBoard.objects.get(user=user, id=data.get('board'))
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
        board = ShopifyBoard.objects.get(user=user, id=data.get('board'))
        board.delete()
        return JsonResponse({
            'status': 'ok'
        })

    if method == 'POST' and target == 'board-empty':
        board = ShopifyBoard.objects.get(user=user, id=data.get('board'))
        board.products.clear()
        return JsonResponse({
            'status': 'ok'
        })

    if method == 'POST' and target == 'variant-image':
        r = requests.put(data.get('url'), json=json.loads(data.get('data')))

        return JsonResponse({
            'status': 'ok'
        })

    if method == 'GET' and target == 'board-config':
        board = ShopifyBoard.objects.get(user=user, id=data.get('board'))

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
        board = ShopifyBoard.objects.get(user=user, id=data.get('board'))

        board.title = data.get('store-title')

        board.config = json.dumps({
            'title': data.get('title'),
            'tags': data.get('tags'),
            'type': data.get('type'),
        })

        board.save()

        utils.smart_board_by_board(user, board)

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

    if method == 'POST' and target == 'product-notes':
        product = ShopifyProduct.objects.get(user=user, id=data.get('product'))
        product.notes = data.get('notes')
        product.save()

        return JsonResponse({
            'status': 'ok',
        })
    if method == 'POST' and target == 'product-metadata':
        if not user.profile.can('product_metadata.use'):
            return JsonResponse({'error': 'Your current plan doesn\'t have this feature.'})

        product = ShopifyProduct.objects.get(user=user, id=data.get('product'))
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
        product = ShopifyProduct.objects.get(user=user, id=data.get('product'))

        upload = UserUpload(user=user, product=product, url=data.get('url'))
        upload.save()

        return JsonResponse({
            'status': 'ok',
        })

    if method == 'POST' and target == 'product-duplicate':
        product = ShopifyProduct.objects.get(user=user, id=data.get('product'))
        duplicate_product = ShopifyProduct.objects.get(user=user, id=data.get('product'))

        duplicate_product.pk = None
        duplicate_product.parent_product = product
        duplicate_product.shopify_export = None
        duplicate_product.stat = 0
        duplicate_product.save()

        return JsonResponse({
            'status': 'ok',
            'product': {
                'id': duplicate_product.id,
                'url': reverse('product_view', args=[duplicate_product.id])
            }
        })

    if method == 'GET' and target == 'user-config':
        config = user.profile.get_config()
        if not user.can('auto_margin.use'):
            for i in ['auto_margin', 'auto_margin_cents', 'auto_compare_at', 'auto_compare_at_cents']:
                if i in config:
                    del config[i]
        else:
            # make sure this fields are populated so the extension can display them
            for i in ['auto_margin', 'auto_margin_cents', 'auto_compare_at', 'auto_compare_at_cents']:
                if i not in config:
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

        if user.can('amazon_import.use'):
            config['amazon_import'] = True

        if user.can('sammydress_import.use'):
            config['sammydress_import'] = True

        if user.can('ebay_import.use'):
            config['ebay_import'] = True

        return JsonResponse(config)

    if method == 'POST' and target == 'user-config':
        config = {}

        for key in data:
            if not data[key]:
                continue

            if key in ['auto_margin', 'auto_compare_at']:
                if not data.get(key).endswith('%'):
                    config[key] = data[key] + '%'
            if key in ['auto_margin_cents', 'auto_compare_at_cents']:
                try:
                    config[key] = int(data[key])
                except:
                    config[key] = ''

            if key in ['make_visisble', 'epacket_shipping']:
                config[key] = bool(data.get(key))

            if key not in config:  # In case the second if above is not true
                config[key] = data[key]

        user.profile.config = json.dumps(config)
        user.profile.save()

        return JsonResponse({'status': 'ok'})

    if method == 'POST' and target == 'fulfill-order':
        try:
            store = ShopifyStore.objects.get(user=user, id=data.get('fulfill-store'))
        except:
            return JsonResponse({'error': 'Store not found'})

        tracking = data.get('fulfill-traking-number')
        if not tracking:
            tracking = None

        api_data = {
            "fulfillment": {
                "tracking_number": tracking,
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
                d = rep.json()
                errors = [k + ': ' + ''.join(d['errors'][k]) for k in d['errors']]
                return JsonResponse({'error': '[Shopify API Error] ' + ' | '.join(errors)})
            except:
                try:
                    d = rep.json()
                    return JsonResponse({'error': 'Shopify API Error: ' + d['errors']})
                except:
                    return JsonResponse({'error': 'Shopify API Error'})

    if method == 'GET' and target == 'product-variant-image':
        try:
            store = ShopifyStore.objects.get(user=user, id=data.get('store'))
        except:
            return JsonResponse({'error': 'Store not found'})

        image = utils.get_shopify_variant_image(store, data.get('product'), data.get('variant'))

        if image:
            return JsonResponse({
                'status': 'ok',
                'image': image
            })

    if method == 'POST' and target == 'variants-mapping':
        product = ShopifyProduct.objects.get(user=user, id=data.get('product'))

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
        shopify_orders = ShopifyOrder.objects.filter(user=user, hidden=False).order_by('updated_at')

        if not data.get('order_id') and not data.get('line_id'):
            shopify_orders = shopify_orders[:20]

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
            ShopifyOrder.objects.filter(user=user, id__in=[i['id'] for i in orders]) \
                                .update(check_count=F('check_count')+1, updated_at=timezone.now())

        return JsonResponse(orders, safe=False)

    if method == 'POST' and target == 'order-fulfill':
        # Mark Order as Ordered
        order_id = data.get('order_id')
        line_id = data.get('line_id')
        source_id = data.get('aliexpress_order_id')

        order_data = {
            'aliexpress': {
                'order_trade': data.get('aliexpress_order_trade')
            }
        }

        order = ShopifyOrder(user=user,
                             order_id=order_id,
                             line_id=line_id,
                             source_id=source_id,
                             data=json.dumps(order_data))
        order.save()

        store = data.get('store')
        if store:
            store = ShopifyStore.objects.get(id=store, user=user)
            order_line = utils.get_shopify_order_line(store, order_id, line_id)
            if order_line:
                note = 'Aliexpress Order ID: {0}\n' \
                       'http://trade.aliexpress.com/order_detail.htm?orderId={0}\n' \
                       'Shopify Product: {1} / {2}'.format(source_id, order_line.get('name'),
                                                           order_line.get('variant_title'))
            else:
                note = 'Aliexpress Order ID: {0}\n' \
                       'http://trade.aliexpress.com/order_detail.htm?orderId={0}\n'.format(source_id)

            utils.add_shopify_order_note(store, order_id, note)

            order.store = store
            order.save()

        return JsonResponse({'status': 'ok'})

    if method == 'DELETE' and target == 'order-fulfill':
        order_id = data.get('order_id')
        line_id = data.get('line_id')

        orders = ShopifyOrder.objects.filter(user=user, order_id=order_id, line_id=line_id)
        if orders.count():
            orders.delete()
            return JsonResponse({'status': 'ok'})
        else:
            return JsonResponse({'error': 'Order not found.'})

    if method == 'POST' and target == 'order-fulfill-update':
        order = ShopifyOrder.objects.get(id=data.get('order'), user=user)
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

    if method == 'POST' and target == 'order-add-note':
        # Append to the Order note
        store = ShopifyStore.objects.get(id=data.get('store'), user=user)

        if utils.add_shopify_order_note(store, data.get('order_id'), data.get('note')):
            return JsonResponse({'status': 'ok'})
        else:
            return JsonResponse({'error': 'Shopify API Error'})

    if method == 'POST' and target == 'order-note':
        # Change the Order note
        store = ShopifyStore.objects.get(id=data.get('store'), user=user)

        if utils.set_shopify_order_note(store, data.get('order_id'), data['note']):
            return JsonResponse({'status': 'ok'})
        else:
            return JsonResponse({'error': 'Shopify API Error'})

    if method == 'POST' and target == 'order-fullfill-hide':
        order = ShopifyOrder.objects.get(id=data.get('order'), user=user)
        order.hidden = data.get('hide', False)
        order.save()

        return JsonResponse({'status': 'ok'})

    if method == 'GET' and target == 'find-product':
        try:
            product = ShopifyProduct.objects.get(user=user, shopify_export__shopify_id=data.get('product'))
            return JsonResponse({
                'status': 'ok',
                'url': 'http://app.shopifiedapp.com{}'.format(reverse('product_view', args=[product.id]))
            })
        except:
            return JsonResponse({'error': 'Product not found'})

    if method == 'POST' and 'generate-reg-link':
        if not user.is_superuser:
            return JsonResponse({'error': 'Unauthorized API call'})

        plan = GroupPlan.objects.get(id=data.get('plan'))
        reg = utils.generate_plan_registration(plan, {
            'email': data.get('email')
        })

        return JsonResponse({
            'status': 'ok',
            'hash': reg.register_hash
        })

    if method == 'GET' and target == 'product-original-desc':
        try:
            product = ShopifyProduct.objects.get(id=data.get('product'), user=user)
            return HttpResponse(json.loads(product.original_data)['description'])
        except:
            return HttpResponse('')

    return JsonResponse({'error': 'Non-handled endpoint'})


def webhook(request, provider, option):
    if provider == 'paylio' and request.method == 'POST':
        if option not in ['vip-elite', 'elite', 'pro', 'basic']:
            raise Http404('Page not found..')

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
            send_mail(subject='Shopified App: Webhook exception',
                      recipient_list=['chase@rankengine.com', 'ma7dev@gmail.com'],
                      from_email='chase@rankengine.com',
                      message='EXCEPTION: {}\nGET: {}\nPOST: {}\nMETA: \n\t{}'.format(repr(e),
                              repr(request.GET.urlencode()),
                              repr(request.POST.urlencode()),
                              '\n\t'.join(re.findall("'[^']+': '[^']+'", repr(request.META)))))

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
                      from_email='chase@rankengine.com',
                      message=email_html,
                      html_message=email_html)

            utils.slack_invite(data)

            send_mail(subject='Shopified App: New Registration',
                      recipient_list=['chase@rankengine.com'],
                      from_email=settings.DEFAULT_FROM_EMAIL,
                      message='A new registration link was generated and send to a new user.\n\nMore information:\n{}'.format(
                          utils.format_data(data)))

            return HttpResponse('ok')
        elif status in ['canceled', 'refunded']:
            try:
                user = User.objects.get(email=data['email'])

                free_plan = GroupPlan.objects.get(register_hash=plan_map['free'])
                user.profile.plan = free_plan
                user.profile.save()

                data['previous_plan'] = plan.title
                data['new_plan'] = free_plan.title

                send_mail(subject='Shopified App: Cancel/Refund',
                          recipient_list=['chase@rankengine.com'],
                          from_email=settings.DEFAULT_FROM_EMAIL,
                          message='A Shopified App User has canceled his/her subscription.\n\nMore information:\n{}'.format(
                              utils.format_data(data)))

                return HttpResponse('ok')

            except Exception as e:
                send_mail(subject='Shopified App: Webhook Cancel/Refund exception',
                          recipient_list=['chase@rankengine.com', 'ma7dev@gmail.com'],
                          from_email='chase@rankengine.com',
                          message='EXCEPTION: {}\nGET: {}\nPOST: {}\nMETA: \n\t{}'.format(repr(e),
                                  repr(request.GET.urlencode()),
                                  repr(request.POST.urlencode()),
                                  '\n\t'.join(re.findall("'[^']+': '[^']+'", repr(request.META)))))
                raise Http404('Error during proccess')

    elif provider == 'jvzoo':
        try:
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

            if request.method == 'GET':
                return HttpResponse('<i>JVZoo</i> Webhook for <b>{}</b>'.format(plan.title))
            elif request.method != 'POST':
                raise Exception('Unexcpected HTTP Method: {}'.request.method)

            params = dict(request.POST.iteritems())
            secretkey = settings.JVZOO_SECRET_KEY

            # verify and parse post
            utils.jvzoo_verify_post(params, secretkey)
            data = utils.jvzoo_parse_post(params)

            trans_type = data['trans_type']
            if trans_type not in ['SALE', 'BILL', 'RFND', 'CGBK', 'INSF']:
                raise Exception('Unknown Transaction Type: {}'.format(trans_type))

            if trans_type == 'SALE':
                reg = utils.generate_plan_registration(plan, {'data': data, 'jvzoo': params})
                data['reg_hash'] = reg.register_hash
                data['plan_title'] = plan.title

                template_file = os.path.join(settings.BASE_DIR, 'app', 'data', 'emails', 'webhook_register.html')
                template = Template(open(template_file).read())

                ctx = Context(data)

                email_html = template.render(ctx)
                email_html = email_html.replace('\n', '<br />')

                send_mail(subject='Your Shopified App Access',
                          recipient_list=[data['email']],
                          from_email='chase@rankengine.com',
                          message=email_html,
                          html_message=email_html)

                utils.slack_invite(data)

                # email_info = 'A new registration link was generated and send to a new user.'
                # email_info = '\n\nMore information:{}\n{}'.format(email_info, utils.format_data(params), utils.format_data(data))
                # send_mail(subject='Shopified App: New Registration',
                #           recipient_list=['ma7dev@gmail.com'],
                #           from_email='chase@rankengine.com',
                #           message=email_info)

                data.update(params)

                payment = PlanPayment(fullname=data['fullname'],
                                      email=data['email'],
                                      provider='JVZoo',
                                      transaction_type=trans_type,
                                      payment_id=params['ctransreceipt'],
                                      data=json.dumps(data))
                payment.save()

                return JsonResponse({'status': 'ok'})

            elif trans_type == 'BILL':
                payment = PlanPayment(fullname=data['fullname'],
                                      email=data['email'],
                                      provider='JVZoo',
                                      transaction_type=trans_type,
                                      payment_id=params['ctransreceipt'],
                                      data=json.dumps(data))
                payment.save()

            elif trans_type in ['RFND', 'CGBK', 'INSF']:
                user = User.objects.get(email=data['email'])

                free_plan = GroupPlan.objects.get(register_hash=plan_map['free'])
                user.profile.plan = free_plan
                user.profile.save()

                data['previous_plan'] = plan.title
                data['new_plan'] = free_plan.title

                payment = PlanPayment(fullname=data['fullname'],
                                      email=data['email'],
                                      user=user,
                                      provider='JVZoo',
                                      transaction_type=trans_type,
                                      payment_id=params['ctransreceipt'],
                                      data=json.dumps(data))
                payment.save()

                email_info = ('A Shopified App User has canceled his/her subscription.\n<br>'
                              'More information:\n<br>'
                              '<a href="http://app.shopifiedapp.com/admin/leadgalaxy/planpayment/{0}/">'
                              'http://app.shopifiedapp.com/admin/leadgalaxy/planpayment/{0}/'
                              '</a>').format(payment.id)

                send_mail(subject='Shopified App: Cancel/Refund',
                          recipient_list=['chase@rankengine.com'],
                          from_email=settings.DEFAULT_FROM_EMAIL,
                          message=email_info,
                          html_message=email_info)

                return HttpResponse('ok')

        except Exception as e:
            print 'Exception:', e
            traceback.print_exc()
            send_mail(subject='[Shopified App] JVZoo Webhook Exception',
                      recipient_list=['chase@rankengine.com', 'ma7dev@gmail.com'],
                      from_email=settings.DEFAULT_FROM_EMAIL,
                      message='EXCEPTION: {}\nGET:\n{}\nPOST:\n{}\nMETA:\n{}'.format(
                              traceback.format_exc(),
                              utils.format_data(dict(request.GET.iteritems()), False),
                              utils.format_data(dict(request.POST.iteritems()), False),
                              utils.format_data(request.META, False)))

            return JsonResponse({'error': 'Server '}, status=500)

        return JsonResponse({'status': 'ok', 'warning': 'Unknown'})

    elif provider == 'shopify' and request.method == 'POST':
        try:
            # Shopify send a JSON POST request
            shopify_product = json.loads(request.body)

            product = None
            token = request.GET['t']
            store = ShopifyStore.objects.get(id=request.GET['store'])

            if token != utils.webhook_token(store.id):
                raise Exception('Unvalide token: {} <> {}'.format(
                    token, utils.webhook_token(store.id)))

            try:
                product = ShopifyProduct.objects.get(
                    user=store.user,
                    shopify_export__shopify_id=shopify_product['id'])
            except:
                return JsonResponse({'status': 'ok', 'warning': 'Processing exception'})

            product_data = json.loads(product.data)

            if option == 'products-update':  # / is converted to - in utils.create_shopify_webhook
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

                ShopifyWebhook.objects.filter(token=token, store=store, topic=option.replace('-', '/')).update(
                    call_count=F('call_count')+1)

                # Delete Product images cache
                ShopifyProductImage.objects.filter(store=store,
                                                   product=shopify_product['id']).delete()

                return JsonResponse({'status': 'ok'})

            elif option == 'products-delete':  # / is converted to - in utils.create_shopify_webhook
                if product.shopify_export:
                    product.shopify_export.delete()

                ShopifyWebhook.objects.filter(token=token, store=store, topic=option.replace('-', '/')).update(
                    call_count=F('call_count')+1)

                ShopifyProductImage.objects.filter(store=store,
                                                   product=shopify_product['id']).delete()

                return JsonResponse({'status': 'ok'})
            else:
                raise Exception('WEBHOOK: options not found: {}'.format(option))
        except:
            print 'WEBHOOK: exception:'
            traceback.print_exc()
            return JsonResponse({'status': 'ok', 'warning': 'Processing exception'})
    elif provider == 'price-notification' and request.method == 'POST':
        product_id = request.GET['product']
        product = ShopifyProduct.objects.get(id=product_id)

        product_change = AliexpressProductChange(product=product, user=product.user, data=request.body)
        product_change.save()

        utils.product_change_notify(product.user)

        return JsonResponse({'status': 'ok'})

    else:
        return JsonResponse({'status': 'ok', 'warning': 'Unknown provider'})


def get_product(request, filter_products, post_per_page=25, sort=None, store=None):
    products = []
    paginator = None
    page = request.GET.get('page', 1)

    res = ShopifyProduct.objects.select_related('store').prefetch_related('shopifyboard_set').filter(user=request.user)
    if store:
        if store == 'c':  # connected
            res = res.exclude(shopify_export__isnull=True)
        elif store == 'n':  # non-connected
            res = res.filter(shopify_export__isnull=True)
        else:
            res = res.filter(shopify_export__store=store)

    if not filter_products and not sort:
        paginator = Paginator(res, post_per_page)

        page = min(max(1, int(page)), paginator.num_pages)
        page = paginator.page(page)
        res = page

    for i in res:
        p = {
            'qelem': i,
            'id': i.id,
            'store': i.store,
            'stat': i.stat,
            'shopify_url': i.shopify_link(),
            'user': request.user,
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
            paginator = Paginator(products, post_per_page)

            page = min(max(1, int(page)), paginator.num_pages)
            page = paginator.page(page)

            products = page.object_list

    return products, paginator, page


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
    args = {
        'request': request,
        'filter_products': (request.GET.get('f') == '1'),
        'post_per_page': utils.safeInt(request.GET.get('ppp'), 25),
        'sort': request.GET.get('sort'),
        'store': request.GET.get('store', 'n')
    }

    if args['filter_products'] and not request.user.profile.can('product_filters.use'):
        return render(request, 'upgrade.html')

    products, paginator, page = get_product(**args)

    if not tpl or tpl == 'grid':
        tpl = 'product.html'
    else:
        tpl = 'product_table.html'

    return render(request, tpl, {
        'paginator': paginator,
        'current_page': page,
        'filter_products': args['filter_products'],
        'products': products,
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
        product = get_object_or_404(ShopifyProduct, id=pid, user=request.user)

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

    if not request.user.profile.can('product_variant_setup.use'):
        return render(request, 'upgrade.html')

    store = get_object_or_404(ShopifyStore, id=store_id, user=request.user)

    product = utils.get_shopify_product(store, pid)

    if not product:
        messages.error(request, 'Product not found in Shopify')
        return HttpResponseRedirect('/')

    return render(request, 'variants_edit.html', {
        'store': store,
        'product_id': pid,
        'product': product,
        'page': 'product',
        'breadcrumbs': [{'title': 'Products', 'url': '/product'}, 'Edit Variants']
    })


@login_required
def product_mapping(request, store_id, product_id):
    product = get_object_or_404(ShopifyProduct, user=request.user, id=product_id)

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
    if not request.user.profile.can('bulk_editing.use'):
        return render(request, 'upgrade.html')

    args = {
        'request': request,
        'filter_products': (request.GET.get('f') == '1'),
        'post_per_page': utils.safeInt(request.GET.get('ppp'), 25),
        'sort': request.GET.get('sort'),
        'store': 'n'
    }

    if args['filter_products'] and not request.user.profile.can('product_filters.use'):
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
def boards(request):
    boards = []
    for b in request.user.shopifyboard_set.all():
        board = {
            'id': b.id,
            'title': b.title,
            'products': []
        }

        for i in b.products.all():
            p = {
                'id': i.id,
                'store': i.store,
                'stat': i.stat,
                'shopify_url': i.shopify_link(),
                'user': i.user,
                'created_at': i.created_at,
                'updated_at': i.updated_at,
                'product': json.loads(i.data),
            }

            try:
                if 'aliexpress' in p['product'].get('original_url', '').lower():
                    p['source'] = 'AliExpress'
                elif 'alibaba' in p['product'].get('original_url', '').lower():
                    p['source'] = 'AliBaba'
            except:
                pass

            if 'images' not in p['product'] or not p['product']['images']:
                p['product']['images'] = []

            p['price'] = '$%.02f' % utils.safeFloat(p['product'].get('price'))

            p['images'] = p['product']['images']
            board['products'].append(p)

        boards.append(board)

    return render(request, 'boards.html', {
        'boards': boards,
        'page': 'boards',
        'breadcrumbs': ['Boards']
    })


@login_required
def get_shipping_info(request):
    aliexpress_id = request.GET.get('id')
    product = request.GET.get('product')
    product = ShopifyProduct.objects.get(user=request.user, id=request.GET.get('product', 0))

    r = requests.get(url="http://freight.aliexpress.com/ajaxFreightCalculateService.htm?",
                     params={
                         'f': 'd',
                         'productid': aliexpress_id,
                         'userType': 'cnfm',
                         'country': 'US',
                         'province': '',
                         'city': '',
                         'count': '1',
                         'currencyCode': 'USD',
                         'sendGoodsCountry': ''
                     })

    try:
        shippement_data = json.loads(r.text[1:-1])
    except:
        shippement_data = {}

    product_data = json.loads(product.data)

    if 'store' in product_data:
        store = product_data['store']
    else:
        store = None

    return render(request, 'shippement_info.html', {
        'info': shippement_data,
        'store': store
    })


@login_required
def acp_users_list(request):
    if not request.user.is_superuser:
        return HttpResponseRedirect('/')

    if request.GET.get('plan', None):
        users = User.objects.select_related('profile', 'profile__plan') \
            .prefetch_related('shopifyproduct_set', 'shopifystore_set') \
            .filter(profile__plan_id=request.GET.get('plan'))
        users_count = User.objects.filter(profile__plan_id=request.GET.get('plan')).count()
    else:
        users = User.objects.select_related('profile', 'profile__plan')

        if request.GET.get('products'):
            users = users.prefetch_related('shopifyproduct_set', 'shopifystore_set')

        users_count = User.objects.count()

    plans = GroupPlan.objects.all()

    return render(request, 'acp/users_list.html', {
        'users': users,
        'plans': plans,
        'users_count': users_count,
        'show_products': request.GET.get('products'),
        'page': 'acp_users_list',
        'breadcrumbs': ['ACP', 'Users List']
    })


@login_required
def acp_graph(request):
    if not request.user.is_superuser:
        return HttpResponseRedirect('/')

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
    if not request.user.is_superuser:
        return HttpResponseRedirect('/')

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
                        plan = GroupPlan.objects.get(title=p['title'])
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

    plans = GroupPlan.objects.all()
    return render(request, 'acp/groups.html', {
        'plans': plans,
        'page': 'acp_groups',
        'breadcrumbs': ['ACP', 'Plans &amp; Groups']
    })


@login_required
def acp_groups_install(request):
    if not request.user.is_superuser:
        return HttpResponseRedirect('/')

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
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'User login required'})

    q = request.GET.get('query', '')

    if target == 'types':
        types = []
        for product in request.user.shopifyproduct_set.all():
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
        for product in request.user.shopifyproduct_set.all():
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


def upgrade_required(request):
    return render(request, 'upgrade.html')


@login_required
def save_image_s3(request):
    """Saves the image in img_url into S3 with the name img_name"""
    if not request.user.profile.can('aviary_photo_editor.use'):
        return render(request, 'upgrade.html')

    import boto
    import urllib2
    import StringIO
    from boto.s3.key import Key

    AWS_ACCESS_KEY = os.environ.get('AWS_ACCESS_KEY_ID')
    AWS_SECRET_KEY = os.environ.get('AWS_SECRET_ACCESS_KEY')
    S3_BUCKET = os.environ.get('S3_BUCKET_NAME')

    img_url = request.POST.get('url')
    img_name = 'uploads/u%d/%s' % (request.user.id, img_url.split('/')[-1])

    product = ShopifyProduct.objects.get(user=request.user, id=request.POST.get('product'))

    conn = boto.connect_s3(AWS_ACCESS_KEY, AWS_SECRET_KEY)
    bucket = conn.get_bucket(S3_BUCKET)
    k = Key(bucket)
    k.key = img_name
    fp = StringIO.StringIO(urllib2.urlopen(img_url).read())
    k.set_metadata("Content-Type", 'image/jpeg')
    k.set_contents_from_file(fp)
    k.make_public()

    upload_url = 'http://%s.s3.amazonaws.com/%s' % (S3_BUCKET, img_name)

    upload = UserUpload(user=request.user, product=product, url=upload_url)
    upload.save()

    return JsonResponse({
        'status': 'ok',
        'url': upload_url
    })


@login_required
def orders_view(request):
    if not request.user.profile.can('orders.use'):
        return render(request, 'upgrade.html')

    stores = []
    all_orders = []
    store = None
    post_per_page = utils.safeInt(request.GET.get('ppp'), 20)
    page = utils.safeInt(request.GET.get('page'), 1)

    if request.GET.get('store'):
        store = ShopifyStore.objects.get(id=request.GET.get('store'), user=request.user)
        request.session['last_store'] = store.id
    else:
        if 'last_store' in request.session:
            store = ShopifyStore.objects.get(id=request.session['last_store'], user=request.user)
        else:
            stores = request.user.profile.get_active_stores()
            if len(stores):
                store = stores[0]

        if not store:
            messages.warning(request, 'Please add at least one store before using the Orders page.')
            return HttpResponseRedirect('/')

    sort = request.GET.get('sort', 'desc')
    status = request.GET.get('status', 'open')
    fulfillment = request.GET.get('fulfillment', 'unshipped')
    financial = request.GET.get('financial', 'any')
    query = request.GET.get('query')

    open_orders = store.get_orders_count(status, fulfillment, financial)
    orders = xrange(0, open_orders)

    paginator = ShopifyOrderPaginator(orders, post_per_page)
    paginator.set_store(store)
    paginator.set_order_limit(post_per_page)
    paginator.set_filter(status, fulfillment, financial)
    paginator.set_reverse_order(sort == 'desc')
    paginator.set_query(utils.safeInt(query, query))

    page = min(max(1, page), paginator.num_pages)
    page = paginator.page(page)

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
    res = ShopifyOrder.objects.filter(user=request.user, order_id__in=orders_ids)
    for i in res:
        orders_list['{}-{}'.format(i.order_id, i.line_id)] = i

    images_list = {}
    res = ShopifyProductImage.objects.filter(store=store, product__in=products_ids)
    for i in res:
        images_list['{}-{}'.format(i.product, i.variant)] = i.image

    for index, order in enumerate(page):
        order['date_str'] = arrow.get(order['created_at']).format('MM/DD/YYYY')
        order['date_tooltip'] = arrow.get(order['created_at']).format('YYYY-MM-DD HH:mm:ss ZZ')
        order['order_url'] = store.get_link('/admin/orders/%d' % order['id'])
        order['store'] = store
        order['placed_orders'] = 0
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
                product = ShopifyProduct.objects.filter(user=request.user, shopify_export__shopify_id=el['product_id'])
                if product.count():
                    product = product.first()
                else:
                    product = None

            if product:
                order['line_items'][i]['product'] = product
                original_url = product.get_original_info()['url']
                try:
                    original_id = re.findall('[/_]([0-9]+).html', original_url)[0]
                    order['line_items'][i]['original_url'] = 'http://www.aliexpress.com/item//{}.html'.format(
                        original_id)
                except:
                    print 'WARNIGN ID NOT FOUND FOR:', original_url

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
                            shipping_address_asci[u'province'] = uk_provinces.get(
                                shipping_address_asci[u'city'].lower().strip(), u'')
                        else:
                            shipping_address_asci[u'province'] = shipping_address_asci[u'country_code']

                    phone = shipping_address_asci.get('phone')
                    if not phone or request.user.get_config('order_default_phone') != 'customer':
                        phone = request.user.get_config('order_phone_number')

                    order_data = {
                        'auto': False,  # False mean step-by-step order placing
                        'variant': el['variant_title'],
                        'quantity': el['fulfillable_quantity'],
                        'shipping_address': shipping_address_asci,
                        'order_id': order['id'],
                        'line_id': el['id'],
                        'store': store.id,
                        'order': {
                            'phone': phone,
                            'note': request.user.get_config('order_custom_note'),
                            'epacket': bool(request.user.get_config('epacket_shipping')),
                        }
                    }

                    if product:
                        try:
                            variants_map = json.loads(product.variants_map)
                        except:
                            variants_map = {}

                        mapped = variants_map.get(str(el['variant_id']))
                        if mapped:
                            order_data['variant'] = ' / '.join(mapped.split(','))

                    order['line_items'][i]['order_data'] = order_data
                except:
                    pass

        all_orders.append(order)

    tpl = 'orders_new.html'
    if request.GET.get('table'):
        tpl = 'orders.html'

    return render(request, tpl, {
        'orders': all_orders,
        'store': store,
        'paginator': paginator,
        'current_page': page,
        'open_orders': open_orders,
        'sort': sort,
        'status': status,
        'financial': financial,
        'fulfillment': fulfillment,
        'query': query,
        'page': 'orders',
        'breadcrumbs': ['Orders']
    })


@login_required
def orders_track(request):
    if not request.user.profile.can('orders.use'):
        return render(request, 'upgrade.html')

    store = None
    post_per_page = utils.safeInt(request.GET.get('ppp'), 20)
    page = utils.safeInt(request.GET.get('page'), 1)

    if request.GET.get('store'):
        store = ShopifyStore.objects.get(id=request.GET.get('store'), user=request.user)
        request.session['last_store'] = store.id
    else:
        if 'last_store' in request.session:
            store = ShopifyStore.objects.get(id=request.session['last_store'], user=request.user)
        else:
            stores = request.user.profile.get_active_stores()
            if len(stores):
                store = stores[0]

        if not store:
            messages.warning(request, 'Please add at least one store before using the Orders page.')
            return HttpResponseRedirect('/')

    orders = ShopifyOrder.objects.filter(user=request.user,
                                         store=store,
                                         hidden=(request.GET.get('hidden', False)))

    orders = orders.order_by('-status_updated_at')

    paginator = Paginator(orders, post_per_page)
    page = min(max(1, page), paginator.num_pages)
    page = paginator.page(page)
    orders = page.object_list

    if len(orders):
        orders = utils.get_tracking_orders(store, orders)

    return render(request, 'orders_track.html', {
        'store': store,
        'orders': orders,
        'paginator': paginator,
        'current_page': page,
        'page': 'orders_track',
        'breadcrumbs': [{'title': 'Orders', 'url': '/orders'}, 'Tracking']
    })


@login_required
def products_update(request):
    if not request.user.profile.can('price_changes.use'):
        return render(request, 'upgrade.html')

    show_hidden = 'hidden' in request.GET

    post_per_page = utils.safeInt(request.GET.get('ppp'), 20)
    page = utils.safeInt(request.GET.get('page'), 1)

    changes = AliexpressProductChange.objects.filter(user=request.user, hidden=show_hidden).order_by('-updated_at')
    paginator = Paginator(changes, post_per_page)
    page = min(max(1, page), paginator.num_pages)
    page = paginator.page(page)
    changes = page.object_list

    product_changes = []
    for i in changes:
        change = {'qelem': i}
        change['id'] = i.id
        change['data'] = json.loads(i.data)
        change['changes'] = utils.product_changes_remap(change['data'])

        product_changes.append(change)

    if not show_hidden:
        AliexpressProductChange.objects.filter(user=request.user,
                                               id__in=[i['id'] for i in product_changes]) \
                                       .update(seen=True)

    # Allow sending notification for new changes
    request.user.set_config('product_change_notify', False)

    return render(request, 'products_update.html', {
        'product_changes': product_changes,
        'show_hidden': show_hidden,
        'paginator': paginator,
        'current_page': page,
        'page': 'products_update',
        'breadcrumbs': [{'title': 'Products', 'url': '/product'}, 'Alerts']
    })


@login_required
def acp_users_emails(request):
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


@login_required
def logout(request):
    user_logout(request)
    return redirect('/')


def register(request, registration=None):
    if request.method == 'POST':
        registration = request.POST.get('rid')

    if registration:
        # Convert the hash to a PlanRegistration model
        registration = get_object_or_404(PlanRegistration, register_hash=registration)

    if registration and registration.expired:
        raise Http404('Registration link expired')

    if request.method == 'POST':
        form = RegisterForm(request.POST)
        if form.is_valid():
            new_user = form.save()
            new_profile = utils.create_new_profile(new_user)

            if registration:
                new_profile.plan = registration.plan
                new_profile.save()

                registration.expired = True
                registration.user = new_user
                registration.save()

            messages.info(request, "Thanks for registering. You are now logged in.")
            new_user = authenticate(username=request.POST['username'],
                                    password=request.POST['password1'])

            login(request, new_user)

            return HttpResponseRedirect("/")
    else:
        try:
            initial = {
                'email': json.loads(registration.data).get('email'),
            }
        except:
            initial = {}

        form = RegisterForm(initial=initial)

    return render(request, "registration/register.html", {
        'form': form,
        'registration': registration
    })


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
