import re
import http.cookies as Cookie

import pytz

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.http import HttpResponseRedirect
from django.utils import timezone
from django.utils.deprecation import MiddlewareMixin

from shopified_core.utils import app_link, save_user_ip, encode_params
from lib.exceptions import capture_exception

Cookie.Morsel._reserved['samesite'] = 'SameSite'


class UserIpSaverMiddleware(object):

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated and not request.session.get('is_hijacked_user'):
            try:
                save_user_ip(request)
            except:
                capture_exception(level='warning')

        return self.get_response(request)


class UserEmailEncodeMiddleware(object):

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.method == 'GET':
            if request.GET.get('f') and request.GET.get('title'):
                if self.need_encoding(request, 'title'):
                    return self.encode_param(request, 'title')

            if request.path == '/orders':
                for p in ['query_order', 'query', 'query_customer']:
                    if request.GET.get(p) and self.need_encoding(request, p):
                        return self.encode_param(request, p)

        return self.get_response(request)

    def need_encoding(self, request, name):
        value = request.GET.get(name)

        if '@' in value:
            try:
                validate_email(value)
                return True

            except ValidationError:
                pass

        return False

    def encode_param(self, request, name, value=None):
        if value is None:
            value = request.GET.get(name) or ''

        params = request.GET.copy()
        params[name] = encode_params(value)

        return HttpResponseRedirect('{}?{}'.format(request.path, params.urlencode()))


class CookiesSameSite(MiddlewareMixin):
    CHROME_VALIDATE_REGEX = "Chrome/((5[1-9])|6[0-6])"

    """
    Support for SameSite attribute in Cookies is implemented in Django 2.1 and won't
    be backported to Django 1.11.x.
    This middleware will be obsolete when your app will start using Django 2.1.
    """
    def process_response(self, request, response):
        # same-site = None introduced for Chrome 80 breaks for Chrome 51-66
        # Refer (https://www.chromium.org/updates/same-site/incompatible-clients)
        http_user_agent = request.META.get('HTTP_USER_AGENT') or " "
        if re.search(self.CHROME_VALIDATE_REGEX, http_user_agent):
            return response

        protected_cookies = getattr(
            settings,
            'SESSION_COOKIE_SAMESITE_KEYS',
            set()
        ) or set()

        if not isinstance(protected_cookies, (list, set, tuple)):
            raise ValueError('SESSION_COOKIE_SAMESITE_KEYS should be a list, set or tuple.')

        protected_cookies = set(protected_cookies)
        protected_cookies |= {settings.SESSION_COOKIE_NAME, settings.CSRF_COOKIE_NAME}

        samesite_flag = getattr(
            settings,
            'SESSION_COOKIE_SAMESITE2',
            None
        )

        if not samesite_flag:
            return response

        samesite_flag = samesite_flag.lower()

        if samesite_flag not in {'lax', 'none', 'strict'}:
            raise ValueError('samesite must be "lax", "none", or "strict".')

        samesite_force_all = getattr(
            settings,
            'SESSION_COOKIE_SAMESITE_FORCE_ALL',
            False
        )
        if samesite_force_all:
            for cookie in response.cookies:
                response.cookies[cookie]['samesite'] = samesite_flag
                response.cookies[cookie]['secure'] = True
        else:
            for cookie in protected_cookies:
                if cookie in response.cookies:
                    response.cookies[cookie]['samesite'] = samesite_flag
                    response.cookies[cookie]['secure'] = True

        return response


class TimezoneMiddleware(object):

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        tzname = request.session.get('django_timezone')
        if not tzname:
            if request.user.is_authenticated:
                tzname = request.user.profile.timezone
                request.session['django_timezone'] = request.user.profile.timezone

        if tzname:
            timezone.activate(pytz.timezone(tzname))
        else:
            timezone.deactivate()

        return self.get_response(request)


class PlanSetupMiddleware(object):

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            request.user.profile.ensure_has_plan()

        return self.get_response(request)


class ShopifyScopeCheckMiddleware(object):

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated \
                and request.method == 'GET' \
                and request.path == '/' \
                and not request.session.get('is_hijacked_user') \
                and not request.user.is_subuser:
            if request.user.profile.get_shopify_stores().count() == 1:
                store = request.user.profile.get_shopify_stores().first()
                if store.need_reauthorization():
                    shop_name = store.shop.split('.')[0]
                    return HttpResponseRedirect(app_link('/shopify/install', shop_name, reinstall=store.id, scope=1))

        return self.get_response(request)
