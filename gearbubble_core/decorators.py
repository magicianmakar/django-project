from shopified_core import permissions


def platform_permission_required(func):
    def _func(request, *args, **kwargs):
        if not request.user.can('gearbubble.use'):
            raise permissions.PermissionDenied()
        return func(request, *args, **kwargs)
    return _func


def restrict_subuser_access(func):
    def _func(request, *args, **kwargs):
        if request.user.is_subuser:
            raise permissions.PermissionDenied()
        return func(request, *args, **kwargs)
    return _func


class HasSubuserPermission(object):
    """Checks if the request user has a specified non-store-specific subuser permission"""
    def __init__(self, subuser_permission):
        self._subuser_permission = subuser_permission

    def __call__(self, func):
        def _func(request, *args, **kwargs):
            if not request.user.can(self._subuser_permission):
                raise permissions.PermissionDenied()
            return func(request, *args, **kwargs)
        return _func
