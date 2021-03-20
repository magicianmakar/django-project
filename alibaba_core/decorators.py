from django.db.models import ObjectDoesNotExist
from django.http import JsonResponse

from shopified_core.permissions import user_can_view
from shopified_core.models_utils import get_store_model


def can_access_store(store=False):
    """
    Validate if a store can be accessed by the user calling an api endpoint.

    :param store: If ``True``, will send store as kwarg of method being called

    Usage::

        @can_access_store([store=False])

    Examples::

        @can_access_store
        def post_endpoint(self, request, user, data): pass

        @can_access_store(store=True)
        def post_endpoint(self, request, user, data, store): pass
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            data = args[3]
            try:
                user_store = get_store_model(data.get('store_type')).objects.get(id=data['store_id'])
                user_can_view(args[2], user_store)

                if store is True:
                    kwargs['store'] = user_store
            except ObjectDoesNotExist:
                return JsonResponse({'error': 'Store not found'}, status=404)

            return func(*args, **kwargs)
        return wrapper

    if callable(store):
        return decorator(store)
    else:
        return decorator
