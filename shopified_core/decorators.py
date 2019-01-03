from django.core.exceptions import PermissionDenied


def no_subusers(func):
    def _func(request, *args, **kwargs):
        if request.user.is_subuser:
            raise PermissionDenied('Sub-User can not access this page')
        return func(request, *args, **kwargs)
    return _func
