from django.core.exceptions import PermissionDenied


def add_to_class(cls, name):
    def _decorator(*args, **kwargs):
        cls.add_to_class(name, args[0])
    return _decorator


def no_subusers(func):
    def _func(request, *args, **kwargs):
        if request.user.is_subuser:
            raise PermissionDenied('Sub-User can not access this page')
        return func(request, *args, **kwargs)
    return _func


def restrict_subuser_access(func):
    """ Prevent sub users from using an endpoint """
    def _func(request, *args, **kwargs):
        if request.user.is_subuser:
            raise PermissionDenied()
        return func(request, *args, **kwargs)
    return _func


class HasSubuserPermission:
    """Checks if the request user has a specified non-store-specific subuser permission"""
    def __init__(self, subuser_permission):
        self._subuser_permission = subuser_permission

    def __call__(self, func):
        def _func(request, *args, **kwargs):
            if not request.user.can(self._subuser_permission):
                raise PermissionDenied()
            return func(request, *args, **kwargs)
        return _func


class PlatformPermissionRequired:
    platforms = ['shopify', 'commercehq', 'woocommerce', 'gearbubble', 'groovekart', 'bigcommerce', 'ebay', 'fb', 'google']

    def __init__(self, platform):
        self._platform = platform

    def __call__(self, func):
        def _func(request, *args, **kwargs):
            if self._platform not in PlatformPermissionRequired.platforms:
                raise NotImplementedError("Platform doesn't exist")
            if not request.user.can(f'{self._platform}.use'):
                raise PermissionDenied()
            return func(request, *args, **kwargs)
        return _func
