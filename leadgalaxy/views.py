from django.shortcuts import render, get_object_or_404
from django.http import HttpResponse, HttpResponseRedirect
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib.auth import logout as user_logout
from django.shortcuts import redirect
from django.template import Context, Template
# from django.conf import settings
from django.template.loader import get_template
from django.contrib.auth.models import User, Group
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Q
from django.contrib.auth import authenticate, login
from django.http import JsonResponse
from django.core.paginator import Paginator
from django.core.urlresolvers import reverse

from .models import *
from .forms import *
from app import settings

import httplib2, os, sys, urlparse, urllib2, re, json, requests, hashlib, arrow

def safeInt(v, default=0.0):
    try:
        return int(v)
    except:
        return default

def safeFloat(v, default=0.0):
    try:
        return float(v)
    except:
        return default

def create_new_profile(user):
    plan = GroupPlan.objects.filter(default_plan=1).first()
    profile = UserProfile(user=user, plan=plan)
    profile.save()

    return profile

def smartBoardByProduct(user, product):
    prodct_info = json.loads(product.data)
    prodct_info = {
        'title': prodct_info.get('title', '').lower(),
        'tags': prodct_info.get('tags', '').lower(),
        'type': prodct_info.get('type', '').lower(),
    }

    for i in user.shopifyboard_set.all():
        try:
            config = json.loads(i.config)
        except:
            continue

        product_added = False
        for j in ['title', 'tags', 'type']:
            if product_added:
                break

            if not len(config.get(j, '')) or not len(prodct_info[j]):
                continue

            for f in config.get(j, '').split(','):
                if f.lower() in prodct_info[j]:
                    i.products.add(product)
                    product_added = True

                    break

        if product_added:
            i.save()

def smartBoardByBoard(user, board):
    for product in user.shopifyproduct_set.all():
        prodct_info = json.loads(product.data)
        prodct_info = {
            'title': prodct_info.get('title', '').lower(),
            'tags': prodct_info.get('tags', '').lower(),
            'type': prodct_info.get('type', '').lower(),
        }

        try:
            config = json.loads(board.config)
        except:
            continue

        product_added = False
        for j in ['title', 'tags', 'type']:
            if product_added:
                break

            if not len(config.get(j, '')) or not len(prodct_info[j]):
                continue

            for f in config.get(j, '').split(','):
                if f.lower() in prodct_info[j]:
                    board.products.add(product)
                    product_added = True

                    break

        if product_added:
            board.save()

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

def get_user_from_token(token):
    try:
        access_token = AccessToken.objects.get(token=token)
    except:
        return None

    if len(token) and access_token:
        return access_token.user

    return None

def get_myshopify_link(user, default_store, link):
    stores = [default_store,]
    for i in user.shopifystore_set.all():
        if i not in stores:
            stores.append(i)

    for store in stores:
        handle = link.split('/')[-1]

        r = requests.get(store.get_link('/admin/products.json', api=True), params={'handle': handle}).json()
        if len(r['products']) == 1:
            return store.get_link('/admin/products/{}'.format(r['products'][0]['id']))

    return None

# @login_required
def api(request, target):
    method = request.method
    if method == 'POST':
        data = request.POST
    elif method == 'GET':
        data = request.GET
    else:
        return JsonResponse({'error', 'Unknow method: %s'%method})

    if 'access_token' in data:
        token = data.get('access_token')
        user = get_user_from_token(token)
    else:
        if request.user.is_authenticated:
            user = request.user
        else:
            user = None

    if target not in ['login', 'shopify', 'save-for-later'] and not user:
        return JsonResponse({'error': 'Unauthenticated api call.'})

    if target == 'login':
        username=data.get('username')
        password=data.get('password')

        if '@' in username:
            try:
                username = User.objects.get(email=username).username
            except:
                return JsonResponse({'error': 'Unvalide email or password'})

        user = authenticate(username=username, password=password)
        if user is not None:
            if user.is_active:
                import uuid, md5
                token = str(uuid.uuid4())
                token = md5.new(token).hexdigest()

                access_token = AccessToken(user=user, token=token)
                access_token.save()

                return JsonResponse({
                    'token': token,
                    'user' : {
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
            create_new_profile(new_user)

            user = authenticate(username=form.cleaned_data['username'], password=form.cleaned_data['password1'])
            if user is not None:
                if user.is_active:
                    import uuid, md5
                    token = str(uuid.uuid4())
                    token = md5.new(token).hexdigest()

                    access_token = AccessToken(user=user, token=token)
                    access_token.save()

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

        total_stores = user.profile.plan.stores # -1 mean unlimited
        user_saved_stores = user.shopifystore_set.filter(is_active=True).count()

        if (total_stores > -1) and (user_saved_stores + 1 > total_stores):
            return JsonResponse({
                'error': 'Your current plan allow up to %d linked stores, currently you have %d linked stores.' \
                         %(total_stores, user_saved_stores)
            })

        store = ShopifyStore(title=name, api_url=url, user=user)
        store.save()

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

        stores = []
        for i in user.shopifystore_set.filter(is_active=True):
            stores.append({
                'id': i.id,
                'name': i.title,
                'url': i.api_url
            })

        return JsonResponse(stores, safe=False)

    if method == 'GET' and target == 'product':
        try:
            product = ShopifyProduct.objects.get(id=data.get('product'), user=user)
        except:
            return JsonResponse({'error':'Product not found'})

        return JsonResponse(json.loads(product.data), safe=False)

    if method == 'POST' and target == 'products-info':
        products = {}
        for p in data.getlist('products[]'):
            try:
                product = ShopifyProduct.objects.get(id=p, user=user)
                products[p] = json.loads(product.data)
            except:
                return JsonResponse({'error':'Product not found'})

        return JsonResponse(products, safe=False)

    if method == 'POST' and (target == 'shopify' or target == 'save-for-later'):
        req_data = json.loads(request.body)
        store = req_data['store']

        data = req_data['data']
        original_data = req_data.get('original', '')
        original_url = req_data.get('original_url', '')

        if 'access_token' in req_data:
            token = req_data['access_token']
            user = get_user_from_token(token)

            if not user:
                return JsonResponse({'error': 'Unvalide access token: %s'%(token)})
        else:
            if request.user.is_authenticated:
                user = request.user
            else:
                return JsonResponse({'error': 'Unauthenticated user'})

        try:
            store = ShopifyStore.objects.get(id=store, user=user)
        except:
            return JsonResponse({
                'error': 'Selected store (%s) not found for user: %s'%(store, user.username if user else 'None')
            })

        endpoint = store.api_url + '/admin/products.json'

        product_data = {}
        if target == 'shopify':

            r = requests.post(endpoint, json=json.loads(data))

            try:
                product_data = r.json()['product']
            except:
                try:
                    d = r.json()
                    return JsonResponse({'error': '[Shopify API Error] '+' | '.join([k+': '+''.join(d['errors'][k]) for k in d['errors']])})
                except:
                    return JsonResponse({'error': 'Shopify API Error'})

            pid = r.json()['product']['id']
            url = store.get_link('/admin/products/{}'.format(pid))

            if 'product' in req_data:
                try:
                    product = ShopifyProduct.objects.get(id=req_data['product'], user=user)
                    original_url = product.get_original_info().get('url', '')
                except:
                    return JsonResponse({'error': 'Selected product not found.'})

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

        else: # save for later
            if 'product' in req_data:
                # Saved product update
                try:
                    product = ShopifyProduct.objects.get(id=req_data['product'], user=user)
                except:
                    return JsonResponse({'error': 'Selected product not found.'})

                product.store = store
                product.data = data
                product.stat = 0

            else: # New product to save

                # Check if the user plan allow more product saving
                total_products = user.profile.plan.products # -1 mean unlimited
                user_saved_products = user.shopifyproduct_set.count()

                if (total_products > -1) and (user_saved_products + 1 > total_products):
                    return JsonResponse({
                        'error': 'Your current plan allow up to %d saved products, currently you have %d saved products.' \
                                 %(total_products, user_saved_products)
                    })

                is_active = req_data.get('activate', True)

                product = ShopifyProduct(store=store, user=user, data=data, original_data=original_data, stat=0, is_active=is_active)
                product.notes = req_data.get('notes', '')

            product.save()

            smartBoardByProduct(user, product)

            url = request.build_absolute_uri('/product/%d'%product.id)
            pid = product.id

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

            product_data['title'] = data.get('title[%s]'%p)
            product_data['tags'] = data.get('tags[%s]'%p)
            product_data['price'] = safeFloat(data.get('price[%s]'%p))
            product_data['compare_at_price'] = safeFloat(data.get('compare_at[%s]'%p))
            product_data['type'] = data.get('type[%s]'%p)
            product_data['weight'] = data.get('weight[%s]'%p)
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
                product_data['price'] = safeFloat(data.get('price'))

            if 'compare_at' in data:
                product_data['compare_at_price'] = safeFloat(data.get('compare_at'))

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
            'products':products
        }, safe=False)

    if method == 'POST' and target == 'boards-add':
        total_boards = user.profile.plan.boards # -1 mean unlimited
        user_saved_boards = user.shopifyboard_set.count()

        if (total_boards > -1) and (user_saved_boards + 1 > total_boards):
            return JsonResponse({
                'error': 'Your current plan allow up to %d boards, currently you have %d boards.' \
                         %(total_boards, user_saved_boards)
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

        smartBoardByBoard(user, board)

        return JsonResponse({
            'status': 'ok'
        })

    if method == 'POST' and target == 'change-plan':
        if not user.is_superuser:
            return JsonResponse({'error': 'You don\'t have access to this endpoint'})

        target_user = User.objects.get(id=data.get('user'))
        plan = GroupPlan.objects.get(id=data.get('plan'))


        try:
            profile = target_user.profile
            target_user.profile.plan = plan
        except:
            profile = UserProfile(user=target_user, plan=plan)

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
        if 'myshopify' not in shopify_link.lower():
            shopify_link = get_myshopify_link(user, product.store, shopify_link)
            if not shopify_link:
                return JsonResponse({'error': 'Invalid Custom domain link.'})

        if not product.set_shopify_id_from_url(shopify_link):
            return JsonResponse({'error': 'Invalid Shopify link.'})

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
            for i in ['order_phone_number', 'order_custom_note',]:
                if i in config:
                    del config[i]
        else:
            for i in ['order_phone_number', 'order_custom_note',]:
                if i not in config:
                        config[i] = ''

        if config.get('description_mode') == '':
            config['description_mode'] = 'empty'

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
                "tracking_number": None,
                "line_items": [{
                    "id": int(data.get('fulfill-line-id')),
                    "quantity": int(data.get('fulfill-quantity'))
                }]
            }
        }

        rep = requests.post(
            url=store.get_link('/admin/orders/{}/fulfillments.json'.format(data.get('fulfill-order-id')), api=True),
            json=api_data
        )

        if 'fulfillment' in rep.json():
            # print 'fulfillment:', rep.json()
            return JsonResponse({'status': 'ok'})
        else:
            try:
                d = rep.json()
                return JsonResponse({'error': '[Shopify API Error] '+' | '.join([k+': '+''.join(d['errors'][k]) for k in d['errors']])})
            except:
                try:
                    d = rep.json()
                    return JsonResponse({'error': 'Shopify API Error: ' + d['errors']})
                except:
                    return JsonResponse({'error': 'Shopify API Error'})

    return JsonResponse({'error': 'Unhandled endpoint'})

def get_product(request, filter_products, post_per_page=25, sort=None, store=None):
    products = []
    paginator = None
    page = request.GET.get('page', 1)

    res = ShopifyProduct.objects.select_related('store').prefetch_related('shopifyboard_set').filter(user=request.user)
    if store:
        if store == 'c': # connected
            res = res.exclude(shopify_export__isnull=True)
        elif store == 'n': # non-connected
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
            if 'aliexpress' in p['product'].get('original_url','').lower():
                p['source'] = 'AliExpress'
            elif 'alibaba' in p['product'].get('original_url','').lower():
                p['source'] = 'AliBaba'
        except: pass

        p['price'] = '$%.02f'%safeFloat(p['product']['price'])

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
        price = safeFloat(product['product']['price'])
        min_price = safeFloat(fdata.get('price_min'), -1)
        max_price = safeFloat(fdata.get('price_max'), -1)

        if (min_price>0 and max_price>0):
            accept = (accept and  (min_price <= price) and (price <= max_price))
        elif (min_price>0):
            accept = (accept and (min_price <= price))

        elif (max_price>0):
            accept = (accept and (max_price >= price))

    if fdata.get('type'):
        accept = (accept and fdata.get('type').lower() in product['product'].get('type').lower())

    if fdata.get('tag'):
        accept = (accept and fdata.get('tag').lower() in product['product'].get('tags').lower())
    if fdata.get('visibile'):
        published = (fdata.get('visibile').lower()=='yes')
        accept = (accept and published == bool(product['product'].get('published')))

    return accept

def sorted_products(products, sort):
    sort_reversed = (sort[0] == '-')

    if sort_reversed:
        sort = sort[1:]

    if sort == 'title':
        products = sorted(products,
            cmp=lambda x,y: cmp(x['product']['title'], y['product']['title']),
            reverse=sort_reversed)

    elif sort == 'price':
        products = sorted(products,
            cmp=lambda x,y: cmp(safeFloat(x['product']['price']), safeFloat(y['product']['price'])),
            reverse=sort_reversed)

    return products

@login_required
def products_list(request, tpl='grid'):
    args = {
        'request': request,
        'filter_products': (request.GET.get('f') == '1'),
        'post_per_page': safeInt(request.GET.get('ppp'), 25),
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
    import time, base64, hmac, urllib, arrow, zlib
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
        { "bucket": S3_BUCKET },
        { "acl": "public-read" }
    ]

    policy = {
        # Valid for 3 hours. Change according to your needs
        "expiration": arrow.now().replace(hours=+3).format("YYYY-MM-DDTHH:mm:ss")+'Z',
        "conditions": conditions
    }

    policy_str = json.dumps(policy)
    string_to_sign = base64.encodestring(policy_str).replace('\n', '')

    signature = base64.encodestring(hmac.new(AWS_SECRET_KEY.encode(), string_to_sign.encode('utf8'), sha1).digest()).strip()

    #  /AWS
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

    p['price'] = '$%.02f'%safeFloat(p['product']['price'])

    p['images'] = p['product']['images']
    p['original_url'] = p['product'].get('original_url')

    if (p['original_url'] and len(p['original_url'])):
        if 'aliexpress' in p['original_url'].lower():
            try:
                p['original_product_id'] = re.findall('([0-9]+).html', p['original_url'])[0]
                p['original_product_source'] = 'ALIEXPRESS'
            except: pass

    try:
        if 'aliexpress' in p['product'].get('original_url','').lower():
            p['source'] = 'AliExpress'
        elif 'alibaba' in p['product'].get('original_url','').lower():
            p['source'] = 'AliBaba'
    except: pass

    original = None
    try:
        original = json.loads(product.original_data)
    except: pass

    export = product.shopify_export
    if export and export.shopify_id:
        p['shopify_url'] = export.store.get_link('/admin/products/{}'.format(export.shopify_id))
        p['variant_edit'] = '/product/variants/{}/{}'.format(export.store.id, product.id)

    return render(request, 'product_view.html', {
        'product': p,
        'original': original,
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
    if not request.user.profile.can('product_variant_setup.use'):
        return render(request, 'upgrade.html')

    store = get_object_or_404(ShopifyStore, id=store_id, user=request.user)
    api_url = '%s/admin/products/%s.json'%(store.api_url, pid)

    r = requests.get(api_url)
    product = json.dumps(r.json()['product'])

    return render(request, 'variants_edit.html', {
        'store': store,
        'product_id': pid,
        'product': product,
        'page': 'product',
        'breadcrumbs': [{'title': 'Products', 'url': '/product'}, 'Edit Vatiants']
    })

@login_required
def bulk_edit(request):
    if not request.user.profile.can('bulk_editing.use'):
        return render(request, 'upgrade.html')

    args = {
        'request': request,
        'filter_products': (request.GET.get('f') == '1'),
        'post_per_page': safeInt(request.GET.get('ppp'), 25),
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
                if 'aliexpress' in p['product'].get('original_url','').lower():
                    p['source'] = 'AliExpress'
                elif 'alibaba' in p['product'].get('original_url','').lower():
                    p['source'] = 'AliBaba'
            except: pass

            if 'images' not in p['product'] or not p['product']['images']:
                p['product']['images'] = []

            p['price'] = '$%.02f'%safeFloat(p['product']['price'])

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
        params= {
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
        shippement_data ={}

    product_data = json.loads(product.data)

    if 'store' in product_data:
        store = product_data['store']
    else:
        store = None

    return render(request, 'shippement_info.html',{
        'info': shippement_data,
        'store': store
    })

@login_required
def acp_users_list(request):
    if not request.user.is_superuser:
        return HttpResponseRedirect('/')

    if request.GET.get('plan', None):
        users = User.objects.select_related('profile', 'profile__plan') \
                    .prefetch_related('shopifyproduct_set','shopifystore_set') \
                    .filter(profile__plan_id=request.GET.get('plan'))
        users_count = User.objects.filter(profile__plan_id=request.GET.get('plan')).count()
    else:
        users = User.objects.select_related('profile', 'profile__plan') \
                    .prefetch_related('shopifyproduct_set','shopifystore_set') \
                    .all()
        users_count = User.objects.count()

    plans = GroupPlan.objects.all()

    return render(request, 'acp/users_list.html', {
        'users': users,
        'plans': plans,
        'users_count': users_count,
        'page': 'acp_users_list',
        'breadcrumbs': ['ACP', 'Users List']
    })

@login_required
def acp_graph(request):
    if not request.user.is_superuser:
        return HttpResponseRedirect('/')

    products = ShopifyProduct.objects.all() \
        .extra({'created':'date(%s.created_at)'%ShopifyProduct._meta.db_table}) \
        .values('created') \
        .annotate(created_count=Count('id')) \
        .order_by('-created')

    users = User.objects.all() \
        .extra({'created':'date(%s.date_joined)'%User._meta.db_table}) \
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
                    info = info + '%s: '%perm.name

                    for p in i['plans']:
                        plan = GroupPlan.objects.get(title=p['title'])
                        plan.permissions.add(perm)

                        info = info + '%s, '%plan.title

                    info = info + '<br> '

            messages.success(request, 'Permission import success<br> new permissions: %d<br>%s'%(len(new_permissions), info))
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
            perm = AppPermission(name='%s.view'%name, description='%s | View'%description)
            perm.save()

            perms.append(perm)

        if request.GET.get('perm-use'):
            perm = AppPermission(name='%s.use'%name, description='%s | Use'%description)
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

    if (request.GET.get('confirm', 'no')!='yes'):
        default_count = 0
        vip_count = 0
        for user in users:
            if 'VIP Members' in user.groups.all().values_list('name', flat=True):
                vip_count += 1
            else:
                default_count += 1

        return HttpResponse('Total: %d - Default: %d - VIP: %d'% (default_count+vip_count,default_count,vip_count))

    count = 0
    with transaction.atomic():
        for user in users:
            if 'VIP Members' in user.groups.all().values_list('name', flat=True):
                profile = UserProfile(user=user, plan=vip_plan)
            else:
                profile = UserProfile(user=user, plan=plan)

            profile.save()

            count += 1

    return HttpResponse('Done, changed: %d'%count)

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

        return JsonResponse({'query': q, 'suggestions': [{'value':i, 'data':i} for i in types]}, safe=False)

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

        return JsonResponse({'query': q, 'suggestions': [{'value':i, 'data':i} for i in tags]}, safe=False)
    else:
        return JsonResponse({'error': 'Unknow target'})

@login_required
def upload_file_sign(request):
    import time, base64, hmac, urllib
    from hashlib import sha1

    AWS_ACCESS_KEY = os.environ.get('AWS_ACCESS_KEY_ID')
    AWS_SECRET_KEY = os.environ.get('AWS_SECRET_ACCESS_KEY')
    S3_BUCKET = os.environ.get('S3_BUCKET_NAME')

    object_name = urllib.quote_plus(request.GET.get('file_name'))
    mime_type = request.GET.get('file_type')

    if 'image' not in mime_type.lower():
        return JsonResponse({'error':'None allowed file type'})

    expires = int(time.time()+60*60*24)
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

def login(request):
    user_logout(request)
    return redirect('/')


@login_required
def save_image_s3(request):
    """Saves the image in img_url into S3 with the name img_name"""
    if not request.user.profile.can('aviary_photo_editor.use'):
        return render(request, 'upgrade.html')

    import boto, urllib2, StringIO
    from boto.s3.key import Key

    AWS_ACCESS_KEY = os.environ.get('AWS_ACCESS_KEY_ID')
    AWS_SECRET_KEY = os.environ.get('AWS_SECRET_ACCESS_KEY')
    S3_BUCKET = os.environ.get('S3_BUCKET_NAME')

    img_url = request.POST.get('url')
    img_name = 'uploads/u%d/%s'%(request.user.id, img_url.split('/')[-1])

    product = ShopifyProduct.objects.get(user=request.user, id=request.POST.get('product'))

    conn = boto.connect_s3(AWS_ACCESS_KEY, AWS_SECRET_KEY)
    bucket = conn.get_bucket(S3_BUCKET)
    k = Key(bucket)
    k.key = img_name
    fp = StringIO.StringIO(urllib2.urlopen(img_url).read())
    k.set_metadata("Content-Type", 'image/jpeg')
    k.set_contents_from_file(fp)
    k.make_public()

    upload_url = 'http://%s.s3.amazonaws.com/%s'%(S3_BUCKET, img_name)

    upload = UserUpload(user=request.user, product=product, url=upload_url)
    upload.save()

    return JsonResponse({
        'status': 'ok',
        'url': upload_url
    })

def get_variant_image(store, product_id, variants_id):
    """ product_id: Product ID in Shopify """
    variant = requests.get(store.get_link('/admin/variants/{}.json'.format(variants_id), api=True)).json()
    image_id = variant['variant']['image_id']

    if image_id:
        image = requests.get(store.get_link('/admin/products/{}/images/{}.json'.format(product_id, image_id), api=True)).json()
        return image['image']['src']
    else:
        return None

@login_required
def orders_view(request):
    if not request.user.profile.can('orders.use'):
        return render(request, 'upgrade.html')

    stores = []
    all_orders = []
    if request.GET.get('store'):
        stores.append(ShopifyStore.objects.get(id=request.GET.get('store')))
    else:
        stores = request.user.profile.get_active_stores()

    for store in stores:
        orders = requests.get(store.get_link('/admin/orders.json', api=True)).json()['orders']
        products = {}

        for index, order in enumerate(orders):
            orders[index]['date_str'] = arrow.get(order['created_at']).humanize()
            orders[index]['order_url'] = store.get_link('/admin/orders/%d'%order['id'])
            orders[index]['store'] = store
            for i, el in enumerate((order['line_items'])):
                product = ShopifyProduct.objects.filter(shopify_export__shopify_id=el['product_id'])
                orders[index]['line_items'][i]['variant_link'] = store.get_link(
                    '/admin/products/%d/variants/%d' % (el['product_id'], el['variant_id']))
                orders[index]['line_items'][i]['image'] = get_variant_image(store, el['product_id'], el['variant_id'])

                if product.count():
                    orders[index]['line_items'][i]['product'] = product.first()
                    original_url = product.first().get_original_info()['url']
                    original_id = re.findall('/([0-9]+).html', original_url)[0]
                    orders[index]['line_items'][i]['original_url'] = 'http://www.aliexpress.com/item//{}.html'.format(
                        original_id)

                if request.user.can('auto_order.use'):
                    order_data = {
                        'variant': el['variant_title'],
                        'quantity': el['fulfillable_quantity'],
                        'shipping_address': order['shipping_address'],
                        'order': {
                            'phone': request.user.config('order_phone_number'),
                            'note': request.user.config('order_custom_note'),
                            'epacket': bool(request.user.config('epacket_shipping')),
                        }
                    }

                    order_data = json.dumps(order_data).encode('base64').strip()
                    orders[index]['line_items'][i]['order_data'] = order_data

        for i in orders:
            all_orders.append(i)

    return render(request, 'orders.html', {
        'orders': all_orders,
        'products': products,
        'page': 'orders',
        'breadcrumbs': ['Orders']
    })

@login_required
def logout(request):
    user_logout(request)
    return redirect('/')

def register(request):
    if request.method == 'POST':
        form = RegisterForm(request.POST)
        if form.is_valid():
            new_user = form.save()
            create_new_profile(new_user)

            return HttpResponseRedirect("/")
    else:
        form = RegisterForm()
    return render(request, "registration/register.html", {
        'form': form,
    })
