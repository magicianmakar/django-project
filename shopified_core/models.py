from django.db import models


class StoreBase(models.Model):
    class Meta:
        abstract = True

    list_index = models.IntegerField(default=0)


class SupplierBase(models.Model):
    class Meta:
        abstract = True


class ProductBase(models.Model):
    class Meta:
        abstract = True


class BoardBase(models.Model):
    class Meta:
        abstract = True
        ordering = ['title']


class OrderTrackBase(models.Model):
    class Meta:
        abstract = True
        ordering = ['-created_at']
        index_together = ['store', 'order_id', 'line_id']
