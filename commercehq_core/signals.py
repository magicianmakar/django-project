import json

from django.conf import settings
from django.dispatch import receiver
from django.db.models.signals import post_save

import keen

from commercehq_core.models import CommerceHQProduct


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
            'keen': {
                'addons': [{
                    'name': 'keen:url_parser',
                    'input': {'url': 'source_url'},
                    'output': 'parsed_source_url'
                }]
            },
            'source_url': source_url,
            'store': store.title,
            'store_type': 'CommerceHQ',
            'product_title': instance.title,
            'product_price': instance.price,
            'product_type': instance.product_type,
        }

        keen.add_event('product_created', keen_data)
