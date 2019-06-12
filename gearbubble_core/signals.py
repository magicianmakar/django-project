import json

from django.conf import settings
from django.dispatch import receiver
from django.db.models.signals import post_save

import keen

from gearbubble_core.models import GearBubbleProduct


@receiver(post_save, sender=GearBubbleProduct)
def gear_send_keen_event_for_product(sender, instance, created, **kwargs):
    if not settings.DEBUG and settings.KEEN_PROJECT_ID and created:
        try:
            data = json.loads(instance.data)
            source_url = data.get('original_url')
        except:
            source_url = ''

        if instance.store:
            store = instance.store
        else:
            store = instance.user.models_user.profile.get_gear_stores().first()

        keen_data = {
            'keen': {
                'addons': [{
                    'name': 'keen:url_parser',
                    'input': {'url': 'source_url'},
                    'output': 'parsed_source_url'
                }]
            },
            'source_url': source_url,
            'store': store.title if store else None,
            'store_type': 'GearBubble',
            'product_title': instance.title,
            'product_price': instance.price,
            'product_type': instance.product_type,
        }

        if instance.store:
            keen_data['store'] = instance.store.title

        keen.add_event('product_created', keen_data)
