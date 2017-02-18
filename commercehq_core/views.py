from django.shortcuts import render
from django.contrib.auth.decorators import login_required

from django.views.generic import ListView
from .models import CommerceHQProduct


@login_required
def index_view(request):
    return render(request, 'commercehq/index.html', {})


class ProductsList(ListView):
    model = CommerceHQProduct
    template_name = 'commercehq/products_grid.html'
    context_object_name = 'products'
