from django.db import models

# Create your models here.
from shopified_core.models import OrderTrackBase


class BasketOrderTrack(OrderTrackBase):
    CUSTOM_TRACKING_KEY = 'basket_custom_tracking'
    # no store needed
    store = models.IntegerField(default=0)
    product_id = models.BigIntegerField()
    basket_order_status = models.CharField(max_length=128, blank=True, null=True, default='')

    def __str__(self):
        return f'<BasketOrderTrack: {self.id}>'
