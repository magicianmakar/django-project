from shopified_core import permissions


def feature_permission_required(func):
    def _func(request, *args, **kwargs):
        if not request.user.can('youtube_ads.use'):
            raise permissions.PermissionDenied()
        return func(request, *args, **kwargs)
    return _func
