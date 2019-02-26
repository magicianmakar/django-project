from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

from shopified_core import permissions
from leadgalaxy.models import ShopifyStore
from commercehq_core.models import CommerceHQStore
from woocommerce_core.models import WooStore
from gearbubble_core.models import GearBubbleStore

from stripe_subscription.models import (
    ExtraStore,
    ExtraCHQStore,
    ExtraWooStore,
    ExtraGearStore
)


def get_extra_model_from_store(store_model):
    if isinstance(store_model, ShopifyStore):
        return ExtraStore
    if isinstance(store_model, CommerceHQStore):
        return ExtraCHQStore
    if isinstance(store_model, WooStore):
        return ExtraWooStore
    if isinstance(store_model, GearBubbleStore):
        return ExtraGearStore


def create_extra_store(sender, instance, created):
    if created:
        try:
            can_add, total_allowed, user_count = permissions.can_add_store(instance.user)
            stores_count = instance.user.profile.get_stores_count()

        except User.DoesNotExist:
            return

        if instance.user.profile.plan.is_stripe() \
                and total_allowed > -1 \
                and total_allowed < stores_count:
            extra_store_model = get_extra_model_from_store(instance)
            extra_store_model.objects.create(
                user=instance.user,
                store=instance,
                period_start=timezone.now())


@receiver(post_save, sender=ShopifyStore)
def add_store_signal(sender, instance, created, **kwargs):
    create_extra_store(sender, instance, created)


@receiver(post_save, sender=CommerceHQStore)
def add_chqstore_signal(sender, instance, created, **kwargs):
    create_extra_store(sender, instance, created)


@receiver(post_save, sender=WooStore)
def add_woostore_signal(sender, instance, created, **kwargs):
    create_extra_store(sender, instance, created)


@receiver(post_save, sender=GearBubbleStore)
def add_gearstore_signal(sender, instance, created, **kwargs):
    create_extra_store(sender, instance, created)
