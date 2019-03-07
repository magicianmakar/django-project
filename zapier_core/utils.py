from django.core.cache import cache

from rest_hooks.signals import raw_hook_event
from rest_hooks.models import Hook

from .payload import get_shopify_order_data


def user_have_hooks(user):
    users = cache.get('users_with_webhooks')
    if users is None:
        users = list(set(Hook.objects.all().values_list('user_id', flat=True)))
        cache.set('users_with_webhooks', users, timeout=3600)

    return user.id in users


def send_shopify_order_event(event_name, store, data):
    raw_hook_event.send(
        sender=None,
        event_name=event_name,
        payload=get_shopify_order_data(store, data),
        user=store.user
    )
