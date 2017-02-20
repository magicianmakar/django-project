from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_http_methods

from raven.contrib.django.raven_compat.models import client as raven_client

from .forms import CommerceHQStoreForm

from django.views.generic import ListView
from .models import CommerceHQProduct


@login_required
def index_view(request):
    return render(request, 'commercehq/index.html', {})


class ProductsList(ListView):
    model = CommerceHQProduct
    template_name = 'commercehq/products_grid.html'
    context_object_name = 'products'
