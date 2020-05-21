import json

from django.db.models.signals import pre_save
from django.dispatch import receiver

from .models import PLSupplement


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
