from models import user_seen
from . import settings


class LastSeenMiddleware(object):
    """
        Middlewate to set timestampe when a user
        has been last seen
    """
    def process_request(self, request):
        if request.user.is_authenticated() and not request.session.get('is_hijacked_user'):
            module = None
            user = request.user.models_user

            if '/api/' in request.path:
                module = settings.LAST_SEEN_API_MODULE
            elif '/admin/' in request.path:
                module = settings.LAST_SEEN_ADMIN_MODULE
                user = request.user

            try:
                user_seen(user, module)
            except:
                from raven.contrib.django.raven_compat.models import client as raven_client
                raven_client.captureException(level='warning')


        return None
