import arrow
import jwt
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.http import HttpResponseRedirect, JsonResponse
from shopified_core.utils import get_domain
import simplejson as json


def _generate_jwt_token(user):
    """
    Generates a JSON Web Token that stores this user's ID and has an expiry
    date set to 60 days into the future.
    """
    dt = arrow.utcnow().replace(minutes=1).timestamp

    token = jwt.encode({
        'id': user.id,
        'exp': dt
    }, settings.SSO_SECRET_KEY, algorithm='HS256')

    return token


@login_required
def redirect(request):
    token = _generate_jwt_token(request.user)
    redirect = request.GET.get('redirect', 'http://academy.dropified.com/sso')

    if not settings.DEBUG and get_domain(redirect) != 'dropified' and get_domain(redirect, full=True) != 'challengedev.wpengine.com':
        return JsonResponse({'error': 'Domain is not allowed'}, status=403)

    return HttpResponseRedirect('{}?token={}'.format(redirect, token))


def validate(request):
    token = request.POST.get('token')
    if not token:
        return JsonResponse({'error': 'Token is not set'}, status=401)

    try:
        info = jwt.decode(token, settings.SSO_SECRET_KEY, algorithms=['HS256'])
    except:
        return JsonResponse({'error': 'Token is not valid'}, status=406)

    now = arrow.utcnow().timestamp

    if now > info['exp']:
        return JsonResponse({'error': 'Token have expired'}, status=406)

    user = User.objects.get(id=info['id'])

    permissions = request.POST.get('permissions')
    response_permissions = {}
    try:
        permissions = json.loads(permissions)
        for permission in permissions:
            response_permissions[permission] = user.can(permission)
    except:
        pass

    info.update({
        'email': user.email,
        'first_name': user.first_name,
        'last_name': user.last_name,
        'is_black': user.can('pls.use') or user.is_staff,
        'response_permissions': response_permissions,
    })

    return JsonResponse(info)
