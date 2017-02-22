from django.http import HttpResponse, Http404


def must_be_authenticated(func):
    def _func(request, *args, **kwargs):
        if not request.user.is_authenticated():
            return HttpResponse(status=401)
        return func(request, *args, **kwargs)
    return _func


def no_subusers(func):
    def _func(request, *args, **kwargs):
        if request.user.is_subuser:
            return HttpResponse(status=403)
        return func(request, *args, **kwargs)
    return _func


def ajax_only(func):
    def _func(request, *args, **kwargs):
        if not request.is_ajax():
            raise Http404
        return func(request, *args, **kwargs)
    return _func
