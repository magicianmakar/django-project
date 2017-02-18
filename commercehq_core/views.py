from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_http_methods

from raven.contrib.django.raven_compat.models import client as raven_client

from .forms import CommerceHQStoreForm


@login_required
def index_view(request):
    return render(request, 'commercehq/index.html', {})


@require_http_methods(['GET', 'POST'])
@csrf_protect
@login_required
def api(request, target):
    if request.method == 'POST' and target == 'add-store':
        form = CommerceHQStoreForm(request.POST)
        if not form.is_valid():
            return JsonResponse({'error': form.errors})
        return JsonResponse({'status': 'ok'})

    return JsonResponse({'error': 'Non-handled endpoint'}, status=501)
