from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.core.exceptions import PermissionDenied
from django.core.cache import cache


@login_required
def last(request):
    if not request.user.is_superuser:
        raise PermissionDenied

    last_message = cache.get('last_product_change_email', 'Not Found')
    return HttpResponse(last_message)
