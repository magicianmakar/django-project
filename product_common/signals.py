from django.db.models.signals import pre_save
from django.dispatch import receiver

from product_common.models import Product


@receiver(pre_save)
def update_product_type(sender, **kwargs):
    if issubclass(sender, Product):
        instance = kwargs['instance']
        # skip signal when runing loaddata (staging.json)
        if kwargs.get('raw', False):
            return False
        assert sender.PRODUCT_TYPE, "Please define PRODUCT_TYPE in class."
        instance.product_type = sender.PRODUCT_TYPE
