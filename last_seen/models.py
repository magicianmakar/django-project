import time
import datetime
from django.db import models
from django.db.models.signals import pre_delete
from django.dispatch import receiver
from django.utils import timezone
from django.core.cache import cache

from . import settings


class LastSeenManager(models.Manager):
    """
        Manager for LastSeen objects

        Provides 2 utility methods
    """

    def seen(self, user, module=settings.LAST_SEEN_DEFAULT_MODULE, force=False, interval=settings.LAST_SEEN_INTERVAL):
        """
            Mask an user last on database seen with optional module

            If module not provided uses LAST_SEEN_DEFAULT_MODULE from settings

            The last seen object is only updates is interval seconds
            passed from last update or force=True
        """
        args = {
            'user': user,
            'module': module,
        }

        try:
            seen, created = self.get_or_create(**args)
        except self.model.MultipleObjectsReturned:
            seen = self.filter(**args).first()
            created = False

            self.filter(**args).exclude(id=seen.id).delete()

        if created:
            return seen

        # if we get the object, see if we need to update
        limit = timezone.now() - datetime.timedelta(seconds=interval)
        if seen.last_seen < limit or force:
            seen.last_seen = timezone.now()
            seen.save()

        return seen

    def when(self, user, module=None):
        args = {'user': user}

        if module:
            args['module'] = module

        return self.filter(**args).latest('last_seen').last_seen


class LastSeen(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    module = models.CharField(default=settings.LAST_SEEN_DEFAULT_MODULE, max_length=20)
    last_seen = models.DateTimeField(default=timezone.now)

    objects = LastSeenManager()

    class Meta:
        ordering = ('-last_seen',)

    def __unicode__(self):
        return u"%s on %s" % (self.user, self.last_seen)


def get_cache_key(module, user):
    """
        Get cache database to cache last database write timestamp
    """
    return "last_seen:%s:%s" % (module, user.pk)


def user_seen(user, module=None, interval=None):
    """
        Mask an user last seen on database if `interval` seconds
        have passed from last database write.

        Uses optional module

        If module not provided uses LAST_SEEN_DEFAULT_MODULE from settings
    """

    if not module:
        module = settings.LAST_SEEN_DEFAULT_MODULE

    cache_key = get_cache_key(module, user)

    if interval is None:
        interval = settings.LAST_SEEN_INTERVAL

    # compute limit to update db
    limit = time.time() - interval
    seen = cache.get(cache_key)
    if not seen or seen < limit:
        cache.set(cache_key, time.time(), interval)

        # mark the database and the cache, if interval is cleared force
        # database write
        if seen == -1:
            LastSeen.objects.seen(user, module=module, interval=interval, force=True)
        else:
            LastSeen.objects.seen(user, module=module, interval=interval)


def clear_interval(user):
    """
        Clear cached interval from last database write timestamp

        Usefuf if you want to force a database write for an user
    """
    keys = {}
    for last_seen in LastSeen.objects.filter(user=user):
        cache_key = get_cache_key(last_seen.module, user)
        keys[cache_key] = -1

    if keys:
        cache.set_many(keys)


@receiver(pre_delete, sender=LastSeen, dispatch_uid='delete_last_seen_cache')
def delete_last_seen_cache(sender, instance, using, **kwargs):
    cache.delete(get_cache_key(settings.LAST_SEEN_DEFAULT_MODULE, instance.user))
    cache.delete(get_cache_key(settings.LAST_SEEN_API_MODULE, instance.user))
    cache.delete(get_cache_key(settings.LAST_SEEN_ADMIN_MODULE, instance.user))
