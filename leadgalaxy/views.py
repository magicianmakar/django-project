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

@login_required
def index(request):
    stores = request.user.shopifystore_set.all()

    return render(request, 'index.html', {
        'stores': stores,
        'clist': 'index',
        'breadcrumbs': ['Dashboard']
    })

def get_user_from_token(token):
    try:
        access_token = AccessToken.objects.get(token=token)
    except:
        return None

    if access_token:
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
        token = data.get('access_token')
        user = get_user_from_token(token)

        if user:
            stores = []
            for i in user.shopifystore_set.all():
                stores.append({
                    'id': i.id,
                    'name': i.title,
                    'url': i.api_url
                })

            return JsonResponse(stores, safe=False)

        return JsonResponse({'error': 'Unvalide access token'})

    if method == 'POST' and target == 'add-store':
        token = data.get('access_token')
        if token:
            user = get_user_from_token(token)
        else:
            if request.user.is_authenticated:
                user = request.user
            else:
                user = None

        name = data.get('name')
        url = data.get('url')

        if user:
            store = ShopifyStore(title=name, api_url=url, user=user)
            store.save()

            stores = []
            for i in user.shopifystore_set.all():
                stores.append({
                    'name': i.title,
                    'url': i.api_url
                })

            return JsonResponse(stores, safe=False)

        return JsonResponse({'error': 'Unvalide access token'})

    if method == 'POST' and target == 'delete-store':
        token = data.get('access_token')
        if token:
            user = get_user_from_token(token)
        else:
            if request.user.is_authenticated:
                user = request.user
            else:
                user = None

        store_id = data.get('store')

        if user:
            ShopifyStore.objects.filter(id=store_id, user=user).delete()

            stores = []
            for i in user.shopifystore_set.all():
                stores.append({
                    'id': i.id,
                    'name': i.title,
                    'url': i.api_url
                })

            return JsonResponse(stores, safe=False)

        return JsonResponse({'error': 'Unvalide access token'})

    if method == 'POST' and target == 'shopify':
        req_data = json.loads(request.body)
        store = req_data['store']


        data = req_data['data']
        token = req_data['access_token']
        user = get_user_from_token(token)

        store = ShopifyStore.objects.get(id=store, user=user)
        endpoint = store.api_url + '/admin/products.json'

        if not user:
            return JsonResponse({'error': 'Unvalide access token'})

        r = requests.post(endpoint, json=json.loads(data))

        import re
        pid = r.json()['product']['id']
        url = re.findall('[^@\.]+\.myshopify\.com', store.api_url)[0]
        url = 'https://%s/admin/products/%d'%(url, pid);

        return JsonResponse({
            'product': {
                'url': url,
                'id': pid
                }
            })

    if method == 'POST' and target == 'save-for-later':
        req_data = json.loads(request.body)
        endpoint = req_data['endpoint']
        data = req_data['data']
        token = req_data['access_token']
        user = get_user_from_token(token)

        if not user:
            return JsonResponse({'error': 'Unvalide access token'})

        r = requests.post(endpoint, json=json.loads(data))

        return JsonResponse(r.json(), safe=False)

    return JsonResponse({'error': 'Unhandled endpoint'})

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
