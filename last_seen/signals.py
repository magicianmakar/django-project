from django.core.cache import cache
from django.db.models.signals import pre_delete
from django.dispatch import receiver

from last_seen.models import LastSeen, get_cache_key
from . import settings


@receiver(pre_delete, sender=LastSeen, dispatch_uid='delete_last_seen_cache')
def delete_last_seen_cache(sender, instance, using, **kwargs):
    cache.delete(get_cache_key(settings.LAST_SEEN_DEFAULT_MODULE, instance.user))
    cache.delete(get_cache_key(settings.LAST_SEEN_API_MODULE, instance.user))
    cache.delete(get_cache_key(settings.LAST_SEEN_ADMIN_MODULE, instance.user))
