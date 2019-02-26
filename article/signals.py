from django.core.cache import cache
from django.db.models.signals import post_save
from django.dispatch import receiver

from article.models import SidebarLink


@receiver(post_save, sender=SidebarLink)
def invalidate_side_bar(sender, instance, created, **kwargs):
    cache.delete_pattern('template.cache.sidebar_link.*')
