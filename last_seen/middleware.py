from models import user_seen
from . import settings


class LastSeenMiddleware(object):
    """
        Middlewate to set timestampe when a user
        has been last seen
    """
    def process_request(self, request):
        if request.user.is_authenticated():
            module = None
            user = request.user.models_user

            if '/api/' in request.path:
                module = settings.LAST_SEEN_API_MODULE
            elif '/admin/' in request.path:
                module = settings.LAST_SEEN_ADMIN_MODULE
                user = request.user

            user_seen(user, module)

        return None
