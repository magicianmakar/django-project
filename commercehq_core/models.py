from urlparse import urlparse

import requests

from django.db import models


class CommerceHQStore(models.Model):
    url = models.URLField()
    title = models.CharField(max_length=300, blank=True, default='')
    api_key = models.CharField(max_length=300)
    api_password = models.CharField(max_length=300)

    class Meta:
        verbose_name = 'CommerceHQ Store'

    def __unicode__(self):
        return urlparse(self.url).hostname


class CommerceHQProduct(models.Model):
    store = models.ForeignKey('CommerceHQStore', related_name='products')
    product_id = models.BigIntegerField()
    title = models.CharField(max_length=300)
    is_multi = models.BooleanField(default=False)
    product_type = models.CharField(max_length=300)
    collections = models.ManyToManyField('CommerceHQCollection', blank=True)
    textareas = models.TextField(blank=True, default='')
    shipping_weight = models.FloatField(blank=True, default=0.0)
    auto_fulfillment = models.BooleanField(default=False)
    track_inventory = models.BooleanField(default=False)
    vendor = models.ForeignKey('CommerceHQProductSupplier', null=True, blank=True)
    tags = models.TextField(blank=True, default='')
    sku = models.CharField(max_length=200, blank=True, default='')
    seo_meta = models.TextField(blank=True, default='')
    seo_title = models.TextField()
    seo_url = models.URLField(blank=True, default='')
    is_template = models.BooleanField(default=False)
    template_name = models.CharField(max_length=300, blank=True, default='')
    is_draft = models.BooleanField(default=False)

    # For single variant
    price = models.FloatField(blank=True, null=True)
    compare_price = models.FloatField(blank=True, null=True)

    # For multi variant
    options = models.TextField(blank=True, null=True)
    variants = models.TextField(blank=True, null=True)

    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()

    def __unicode__(self):
        return self.title


class CommerceHQProductSupplier(models.Model):
    store = models.ForeignKey('CommerceHQStore', related_name='suppliers')
    supplier_name = models.CharField(max_length=300)

    def __unicode__(self):
        return self.supplier_name


class CommerceHQCollection(models.Model):
    store = models.ForeignKey('CommerceHQStore', related_name='collections')
    collection_id = models.BigIntegerField()
    title = models.CharField(max_length=100)
    is_auto = models.BooleanField(default=False)

    def __unicode__(self):
        return self.collection_id




