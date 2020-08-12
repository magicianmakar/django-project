import json

from django.db.models.signals import pre_save
from django.dispatch import receiver

from shopified_core import permissions
from .models import PLSupplement, UserSupplement


@receiver(pre_save, sender=PLSupplement)
def reload_preset_background(sender, instance, **kwargs):
    try:
        obj = sender.objects.get(pk=instance.pk)
    except sender.DoesNotExist:
        pass
    else:
        if obj.mockup_type != instance.mockup_type:
            instance.user_pl_supplements.all().update(
                label_presets=json.dumps(instance.mockup_type.get_label_presets())
            )


@receiver(pre_save, sender=UserSupplement)
def deny_user_supplement_by_plan(sender, instance, **kwargs):
    if not instance.id:
        can_add, total_allowed, user_count = permissions.can_use_unique_supplement(
            instance.user, instance.pl_supplement.id)
        if not can_add:
            raise Exception(f"Your plan allow usage of {total_allowed} "
                            + f"supplements, currently you use {user_count} supplements.")

        can_add, total_allowed, user_count = permissions.can_add_supplement(
            instance.user)
        if not can_add:
            raise Exception(f"Your plan allow up to {total_allowed} "
                            + f"supplements, currently you have {user_count} supplements.")
