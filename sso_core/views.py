from urllib.parse import urlencode

import simplejson as json

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.http import HttpResponseRedirect, JsonResponse
from django.contrib import messages

from shopified_core.utils import jwt_decode, jwt_encode


SITE_CONFIG = {
    'production': [
        {
            'name': 'Dropified Academy',
            'redirect_url': 'http://academy.dropified.com/sso',
            'domain': 'academy.dropified.com',
        },
        {
            'name': 'Dropified deploy',
            'redirect_url': 'http://appdeploy.dropified.com/login',
            'domain': 'appdeploy.dropified.com',
            'validator': lambda user: user.is_staff
        }
    ],
    'development': [
        {
            'name': 'Dropified Academy',
            'redirect_url': 'http://challengedev.wpengine.com/sso',
            'domain': 'challengedev.wpengine.com',
        },
        {
            'name': 'Dropified deploy',
            'redirect_url': 'http://localhost:8080/login',
            'domain': 'localhost:8080',
            'validator': lambda user: user.is_staff
        }
    ],
}


def _generate_jwt_token(user, **kwargs):
    """
    Generates a JSON Web Token that stores this user's ID.
    """

    payload = {'id': user.id}
    if kwargs:
        payload.update(kwargs)

    token = jwt_encode(
        payload=payload,
        key=settings.SSO_SECRET_KEY,
        expire=6
    )

    return token


@login_required
def redirect(request):
    redirect = request.GET.get('redirect')

    config = SITE_CONFIG['development'] if settings.DEBUG else SITE_CONFIG['production']

    for site in config:
        if site['redirect_url'].strip('/') == redirect.strip('/'):
            if site.get('validator'):
                if not site['validator'](request.user):
                    messages.error(request, 'You are not allowed to access this site')
                    return HttpResponseRedirect('/')

            token = _generate_jwt_token(request.user, domain=site['domain'])
            return HttpResponseRedirect(f'{redirect}?{urlencode({"token": token})}')

    messages.error(request, 'Website is not found')
    return HttpResponseRedirect('/')


def validate(request):
    token = request.POST.get('token')
    if not token:
        return JsonResponse({'error': 'Token is not set'}, status=401)

    try:
        info = jwt_decode(token, key=settings.SSO_SECRET_KEY)
    except:
        return JsonResponse({'error': 'Token is not valid'}, status=406)

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
