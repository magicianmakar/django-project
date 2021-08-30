from django.dispatch import receiver
from django.db.models.signals import post_save, post_delete

from bigcommerce_core.models import BigCommerceProduct
from commercehq_core.models import CommerceHQProduct
from groovekart_core.models import GrooveKartProduct
from leadgalaxy.models import ShopifyProduct
from shopified_core.models import ProductBase
from woocommerce_core.models import WooProduct

from .tasks import index_product_task, delete_product_task


@receiver(post_save, sender=ShopifyProduct)
@receiver(post_save, sender=CommerceHQProduct)
@receiver(post_save, sender=WooProduct)
@receiver(post_save, sender=GrooveKartProduct)
@receiver(post_save, sender=BigCommerceProduct)
def product_update_es_signal(sender, instance: ProductBase, created, **kwargs):
    print(f'product_update_es_signal: {type(sender)} => {sender}')
    if instance.user.profile.index_products:
        index_product_task.delay(instance.id, sender.__name__)


@receiver(post_delete, sender=ShopifyProduct)
@receiver(post_delete, sender=CommerceHQProduct)
@receiver(post_delete, sender=WooProduct)
@receiver(post_delete, sender=GrooveKartProduct)
@receiver(post_delete, sender=BigCommerceProduct)
def product_delete_es_signal(sender, instance, **kwargs):
    print(f'product_delete_es_signal: {type(sender)} => {sender} | {kwargs}')
    if instance.user.profile.index_products:
        delete_product_task.delay(instance.id, sender.__name__)
