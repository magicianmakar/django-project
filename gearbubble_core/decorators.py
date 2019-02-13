from shopified_core import permissions


def platform_permission_required(func):
    def _func(request, *args, **kwargs):
        if not request.user.can('gearbubble.use'):
            raise permissions.PermissionDenied()
        return func(request, *args, **kwargs)
    return _func
