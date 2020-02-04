from django.dispatch import receiver
from django.db.models.signals import post_save

from . import models
from . import utils


@receiver(post_save, sender=models.ProductPrice)
def attach_price_to_product(sender, instance, created, **kwargs):
    if not instance.product:
        try:
            product = models.Product.objects.get(skus__icontains=instance.sku)

            models.ProductPrice.objects.filter(id=instance.id).update(product=product)
            price_range = utils.generate_new_price_range(product, instance)
            models.Product.objects.filter(id=product.id).update(price_range=price_range)

        except models.Product.DoesNotExist:
            pass
