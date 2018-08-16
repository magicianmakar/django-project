from rest_hooks.signals import raw_hook_event

from .serializers import ShopifyOrderTrackSerializer, CommerceHQOrderTrackSerializer
from .payload import get_shopify_order_data


def send_shopify_order_event(event_name, store, data):
    raw_hook_event.send(
        sender=None,
        event_name=event_name,
        payload=get_shopify_order_data(store, data),
        user=store.user
    )


def send_order_track_change(order_track, old_source_status, old_source_tracking):
    return None  # disable triggers for track changes
    payload = None
    model_name = order_track.__class__.__name__
    if model_name == 'ShopifyOrderTrack':
        payload = ShopifyOrderTrackSerializer(order_track).data
    elif model_name == 'CommerceHQOrderTrack':
        payload = CommerceHQOrderTrackSerializer(order_track).data

    if payload is not None:
        if order_track.source_status != old_source_status:
            raw_hook_event.send(
                sender=None,
                event_name='order_track_source_status_changed',
                payload=payload,
                user=order_track.user
            )
        if order_track.source_tracking != old_source_tracking:
            raw_hook_event.send(
                sender=None,
                event_name='order_track_source_tracking_changed',
                payload=payload,
                user=order_track.user
            )
    return payload
