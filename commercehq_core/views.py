from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_http_methods
from django.http import HttpResponse
from django.views.generic import ListView

from .models import CommerceHQStore, CommerceHQProduct
from .forms import CommerceHQStoreForm


class ProductsList(ListView):
    model = CommerceHQProduct
    template_name = 'commercehq/products_grid.html'
    context_object_name = 'products'


@login_required
def index_view(request):
    stores = CommerceHQStore.objects.filter(user=request.user.models_user)
    return render(request, 'commercehq/index.html', {'stores': stores})


@require_http_methods(['POST'])
@csrf_protect
@login_required
def store_create(request):
    form = CommerceHQStoreForm(request.POST)

    if form.is_valid():
        store = form.save(commit=False)
        store.user = request.user.models_user
        store.save()
        return HttpResponse(status=201)

    return render(request, 'commercehq/store_create_form.html', {'form': form})


@require_http_methods(['GET', 'POST'])
@csrf_protect
@login_required
def store_update(request, store_id):
    instance = get_object_or_404(CommerceHQStore, user=request.user.models_user, pk=store_id)
    form = CommerceHQStoreForm(request.POST or None, instance=instance)

    if request.method == 'POST' and form.is_valid():
        form.save()
        return HttpResponse(status=201)

    return render(request, 'commercehq/store_update_form.html', {'form': form})


@require_http_methods(['POST'])
@csrf_protect
@login_required
def store_delete(request, store_id):
    instance = get_object_or_404(CommerceHQStore, user=request.user.models_user, pk=store_id)
    instance.delete()

    return HttpResponse()
