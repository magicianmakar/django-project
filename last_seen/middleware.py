from .models import user_seen
from django.http import Http404

from lib.exceptions import capture_exception

from . import settings


class LastSeenMiddleware(object):
    """
        Middlewate to set timestampe when a user
        has been last seen
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path.startswith('/admin/') and not request.user.is_superuser \
                and not request.user.is_staff \
                and not request.session.get('is_hijacked_user'):
            raise Http404

        if request.user.is_authenticated and not request.session.get('is_hijacked_user'):
            module = None
            user = request.user.models_user

            if '/api/' in request.path:
                module = settings.LAST_SEEN_API_MODULE
            elif '/admin/' in request.path:
                module = settings.LAST_SEEN_ADMIN_MODULE
                user = request.user

            try:
                user_seen(user, module=module)
                if request.user.is_subuser and user != request.user:
                    interval = 600 if module is None else None

                    user_seen(request.user, module=module, interval=interval)
            except:
                capture_exception(level='warning')

        return self.get_response(request)
