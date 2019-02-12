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
