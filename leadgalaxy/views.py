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

from .models import *
from .forms import *
from app import settings

import httplib2, os, sys, urlparse, urllib2, re, json, requests, hashlib

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
def index(request):
    stores = request.user.shopifystore_set.filter(is_active=True)

    return render(request, 'index.html', {
        'stores': stores,
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

        ShopifyStore.objects.filter(id=store_id, user=user).update(is_active=False)

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
                    print r.text
                    return JsonResponse({'error': 'Shopify API Error'})

            pid = r.json()['product']['id']
            url = re.findall('[^@\.]+\.myshopify\.com', store.api_url)[0]
            url = 'https://%s/admin/products/%d'%(url, pid);

            if 'product' in req_data:
                try:
                    product = ShopifyProduct.objects.get(id=req_data['product'], user=user)
                except:
                    return JsonResponse({'error': 'Selected product not found.'})

                product.shopify_id = pid
                product.stat = 1
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

                # zip & base64 encode before saving to save space on database
                original_data = original_data.encode('utf-8').encode('zlib').encode('base64')

                product = ShopifyProduct(store=store, user=user, data=data, original_data=original_data, stat=0)
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

    if method == 'POST' and target == 'add-user-upload':
        product = ShopifyProduct.objects.get(user=user, id=data.get('product'))

        upload = UserUpload(user=user, product=product, url=data.get('url'))
        upload.save()

        return JsonResponse({
            'status': 'ok',
        })

    return JsonResponse({'error': 'Unhandled endpoint'})

def get_product(request, filter_products, post_per_page=25):
    products = []
    if filter_products:
        page = ShopifyProduct.objects.filter(user=request.user)
        paginator = None
    else:
        res = ShopifyProduct.objects.filter(user=request.user)
        paginator = Paginator(res, post_per_page)

        page = request.GET.get('page', 1)
        page = min(max(1, int(page)), paginator.num_pages)

        page = paginator.page(page)

    for i in page:
        p = {
            'id': i.id,
            'store': i.store,
            'stat': i.stat,
            'shopify_url': i.shopify_link(),
            'user': i.user,
            'created_at': i.created_at,
            'updated_at': i.updated_at,
            'product': json.loads(i.data),
            'boards': i.shopifyboard_set.all()
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


    if filter_products and len(products):
        paginator = Paginator(products, post_per_page)

        page = request.GET.get('page', 1)
        page = min(max(1, int(page)), paginator.num_pages)

        page = paginator.page(page)
        products = page.object_list


    return products, paginator, page

def accept_product(product, fdata):
    accept = True

    if fdata.get('title'):
        accept = fdata.get('title').lower() in product['product']['title'].lower()
        print 'Check title:', accept

    if fdata.get('price_min') or fdata.get('price_max'):
        price = safeFloat(product['product']['price'])
        min_price = safeFloat(fdata.get('price_min'), -1)
        max_price = safeFloat(fdata.get('price_max'), -1)

        print 'Filter price:', min_price, '<', price, '<', max_price

        if (min_price>0 and max_price>0):
            accept = (accept and  (min_price <= price) and (price <= max_price))
            print 'Check min+max:', accept
        elif (min_price>0):
            accept = (accept and (min_price <= price))
            print 'Check min:', accept

        elif (max_price>0):
            accept = (accept and (max_price >= price))
            print 'Check max:', accept

    if fdata.get('type'):
        accept = (accept and fdata.get('type').lower() in product['product'].get('type').lower())

    if fdata.get('tag'):
        accept = (accept and fdata.get('tag').lower() in product['product'].get('tags').lower())
    if fdata.get('visibile'):
        print 'publish', product['product'].get('published')
        print 'visibile', fdata.get('visibile')
        published = (fdata.get('visibile').lower()=='yes')
        accept = (accept and published == bool(product['product'].get('published')))

    print 'Accept:', accept
    return accept

@login_required
def product(request, tpl='grid'):
    filter_products = (request.GET.get('f') == '1')
    post_per_page = safeInt(request.GET.get('ppp'), 25)

    products, paginator, page = get_product(request, filter_products, post_per_page)

    if not tpl or tpl == 'grid':
        tpl = 'product.html'
    else:
        tpl = 'product_table.html'

    return render(request, tpl, {
        'paginator': paginator,
        'current_page': page,
        'filter_products': filter_products,
        'products': products,
        'page': 'product',
        'breadcrumbs': ['Products']
    })

@login_required
def product_view(request, pid):
    #  AWS
    import time, base64, hmac, urllib, arrow
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
        original = json.loads(product.original_data.decode('base64').decode('zlib'))
    except: pass


    return render(request, 'product_view.html', {
        'product': p,
        'original': original,
        'images_upload': (aws_available and 'VIP' in request.user.profile.plan.title),
        'aws_policy': string_to_sign,
        'aws_signature': signature,
        'aws_key': AWS_ACCESS_KEY,
        'aws_bucket': S3_BUCKET,
        'page': 'product',
        'breadcrumbs': [{'title': 'Products', 'url': '/product'}, 'View']
    })

@login_required
def variants_edit(request, store_id, pid):
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
    filter_products = (request.GET.get('f') == '1')
    post_per_page = safeInt(request.GET.get('ppp'), 25)

    products, paginator, page = get_product(request, filter_products, post_per_page)

    return render(request, 'bulk_edit.html', {
        'products': products,
        'paginator': paginator,
        'current_page': page,
        'filter_products': filter_products,
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
    product = request.GET.get('id')

    r = requests.get(url="http://freight.aliexpress.com/ajaxFreightCalculateService.htm?",
        params= {
            'f': 'd',
            'productid': product,
            'userType': 'cnfm',
            'country': 'US',
            'province': '',
            'city': '',
            'count': '1',
            'currencyCode': 'USD',
            'sendGoodsCountry': ''
    })

    data = json.loads(r.text[1:-1])

    return render(request, 'shippement_info.html',{
        'info': data
    })

@login_required
def acp_users_list(request):
    if not request.user.is_superuser:
        return HttpResponseRedirect('/')

    if request.GET.get('plan', None):
        users = User.objects.filter(profile__plan_id=request.GET.get('plan'))
        users_count = User.objects.filter(profile__plan_id=request.GET.get('plan')).count()
    else:
        users = User.objects.all()
        users_count = User.objects.count()

    plans = GroupPlan.objects.all()

    return render(request, 'acp_users_list.html', {
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

    return render(request, 'acp_graph.html', {
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
        plan = GroupPlan.objects.get(id=request.POST['default-plan'])
        GroupPlan.objects.all().update(default_plan=0)
        plan.default_plan = 1
        plan.save()

    plans = GroupPlan.objects.all()
    return render(request, 'acp_groups.html', {
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

def login(request):
    user_logout(request)
    return redirect('/')

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
