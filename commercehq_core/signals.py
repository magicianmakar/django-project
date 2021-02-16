import json

from django.conf import settings
from django.dispatch import receiver
from django.db.models.signals import post_save
from django.contrib.auth.models import User

from commercehq_core.models import CommerceHQProduct, CommerceHQOrderTrack, CommerceHQStore
from shopified_core.tasks import keen_send_event
from shopified_core.utils import get_domain
from profits.utils import get_costs_from_track
from analytic_events.models import StoreCreatedEvent


@receiver(post_save, sender=CommerceHQOrderTrack, dispatch_uid='chq_sync_aliexpress_fulfillment_cost')
def sync_aliexpress_fulfillment_cost(sender, instance, created, **kwargs):
    try:
        if instance.user.can('profit_dashboard.use'):
            get_costs_from_track(instance, commit=True)

    except User.DoesNotExist:
        pass


@receiver(post_save, sender=CommerceHQProduct)
def chq_send_keen_event_for_product(sender, instance, created, **kwargs):
    if not settings.DEBUG and settings.KEEN_PROJECT_ID and created:
        try:
            data = json.loads(instance.data)
            source_url = data.get('original_url')
        except:
            source_url = ''

        if instance.store:
            store = instance.store
        else:
            store = instance.user.models_user.profile.get_chq_stores().first()

        keen_data = {
            'supplier': get_domain(source_url) if source_url else None,
            'source_url': source_url,
            'store': store.title if store else None,
            'store_type': 'CommerceHQ',
            'product_title': instance.title,
            'product_price': instance.price,
            'product_type': instance.product_type,
        }

        keen_send_event.delay('product_save', keen_data)


@receiver(post_save, sender=CommerceHQStore)
def store_saved(sender, instance, created, **kwargs):
    if created:
        StoreCreatedEvent.objects.create(user=instance.user, platform='CommerceHQ')
