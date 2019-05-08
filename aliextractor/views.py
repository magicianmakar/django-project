from django.contrib.auth.decorators import login_required

from django.shortcuts import render
from django.urls import reverse


@login_required
def index(request):
    if not request.user.can('aliextractor.use'):
        return render(request, 'upgrade.html')

    return render(request, 'aliextractor/index.html', {
        'page': 'aliextractor',
        'selected_menu': 'tools:aliextractor',
        'breadcrumbs': [{'title': 'AliExtractor', 'url': reverse('aliextractor_index')}, 'Dashboard'],
    })
