from django.shortcuts import render, get_object_or_404
from django.http import HttpResponse, HttpResponseRedirect
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib.auth import logout as user_logout
from django.shortcuts import redirect
from django.template import Context, Template
# from django.conf import settings
from django.template.loader import get_template
from django.contrib.auth.models import User
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Q
from django.contrib.auth import authenticate, login
from django.http import JsonResponse

from .models import *
from .forms import *
from app import settings

import httplib2, os, sys, urlparse, urllib2, re, json, requests, hashlib

def safeFloat(v):
    try:
        return float(v)
    except:
        return 0.0

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
    stores = request.user.shopifystore_set.all()

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

                return JsonResponse({'token': token})
                # Redirect to a success page.

        return JsonResponse({'error': 'Unvalide username or password'})

    if method == 'POST' and target == 'register':
        form = RegisterForm(request.POST)
        if form.is_valid():
            new_user = form.save()

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
        for i in user.shopifystore_set.all():
            stores.append({
                'id': i.id,
                'name': i.title,
                'url': i.api_url
            })

        return JsonResponse(stores, safe=False)


    if method == 'POST' and target == 'add-store':
        name = data.get('name')
        url = data.get('url')

        store = ShopifyStore(title=name, api_url=url, user=user)
        store.save()

        stores = []
        for i in user.shopifystore_set.all():
            stores.append({
                'name': i.title,
                'url': i.api_url
            })

        return JsonResponse(stores, safe=False)

    if method == 'POST' and target == 'delete-store':
        store_id = data.get('store')

        ShopifyStore.objects.filter(id=store_id, user=user).delete()

        stores = []
        for i in user.shopifystore_set.all():
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
        else:
            if 'product' in req_data:
                try:
                    product = ShopifyProduct.objects.get(id=req_data['product'], user=user)
                except:
                    return JsonResponse({'error': 'Selected product not found.'})

                product.store = store
                product.data = data
                product.stat = 0

            else:
                original_data = original_data.encode('zlib').encode('base64')

                product = ShopifyProduct(store=store, user=user, data=data, original_data=original_data, stat=0)

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
        product.delete()

        return JsonResponse({'status': 'ok'})

    if method == 'POST' and target == 'bulk-edit':
        for p in data.getlist('product'):
            product = ShopifyProduct.objects.get(id=p)
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
            product = ShopifyProduct.objects.get(id=p)
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
            product = ShopifyProduct.objects.get(id=p)
            # product.shopifyboard_set.clear()
            board.products.add(product)

        board.save()

        return JsonResponse({'status': 'ok'})

    if method == 'POST' and target == 'product-remove-board':
        board = ShopifyBoard.objects.get(user=user, id=data.get('board'))
        products = []
        for p in data.getlist('products[]'):
            product = ShopifyProduct.objects.get(id=p)
            # product.shopifyboard_set.clear()
            board.products.remove(product)

        board.save()

        return JsonResponse({'status': 'ok'})

    if method == 'POST' and target == 'product-board':
        product = ShopifyProduct.objects.get(id=data.get('product'))

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

    return JsonResponse({'error': 'Unhandled endpoint'})

@login_required
def product(request, tpl='grid'):
    products = []
    for i in ShopifyProduct.objects.filter(user=request.user):
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

        p['price'] = '$%.02f'%safeFloat(p['product']['price'])

        if 'images' not in p['product'] or not p['product']['images']:
            p['product']['images'] = []

        p['images'] = p['product']['images']
        products.append(p)

    if not tpl or tpl == 'grid':
        tpl = 'product.html'
    else:
        tpl = 'product_table.html'

    return render(request, tpl, {
        'products': products,
        'page': 'product',
        'breadcrumbs': ['Products']
    })

@login_required
def product_view(request, pid):
    product = get_object_or_404(ShopifyProduct, id=pid, user=request.user)
    p = {
        'id': product.id,
        'store': product.store,
        'user': product.user,
        'created_at': product.created_at,
        'updated_at': product.updated_at,
        'data': product.data,
        'product': json.loads(product.data),
    }

    if 'images' not in p['product'] or not p['product']['images']:
        p['product']['images'] = []

    p['price'] = '$%.02f'%safeFloat(p['product']['price'])

    p['images'] = p['product']['images']
    p['original_url'] = p['product'].get('original_url')

    original = None
    try:
        original = json.loads(product.original_data.decode('base64').decode('zlib'))
    except: pass

    return render(request, 'product_view.html', {
        'product': p,
        'original': original,
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
    products = []
    for i in ShopifyProduct.objects.filter(user=request.user):
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

        if 'images' not in p['product'] or not p['product']['images']:
            p['product']['images'] = []

        p['price'] = '$%.02f'%safeFloat(p['product']['price'])

        p['images'] = p['product']['images']
        products.append(p)

    return render(request, 'bulk_edit.html', {
        'products': products,
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
            return HttpResponseRedirect("/")
    else:
        form = RegisterForm()
    return render(request, "registration/register.html", {
        'form': form,
    })
