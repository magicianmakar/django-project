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
