from django.shortcuts import render, get_object_or_404
from django.http import HttpResponse, HttpResponseRedirect
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect
from django.template import Context, Template
# from django.conf import settings
from django.template.loader import get_template
from django.contrib.auth import logout as user_logout

from xhtml2pdf import pisa

from .models import *
from .forms import *
from app import settings

import httplib2, os, sys, urlparse, urllib2, re, json, requests

@login_required
def index(request):
    return render(request, 'index.html', {})

@login_required
def api(request, target):
    data = request.POST
    if target == 'project':
        return HttpResponse('ok')

    return HttpResponse('error')

@login_required
def logout(request):
    user_logout(request)
    return redirect('index')

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


def JsonResponse(data):
    return HttpResponse(json.dumps(data, sort_keys=True, indent=4),
                        content_type='application/json; charset=UTF-8')

def shopify(request):
    req_data = json.loads(request.body)
    endpoint = req_data['endpoint']
    data = req_data['data']

    r = requests.post(endpoint, json=json.loads(data))

    return JsonResponse(r.json())