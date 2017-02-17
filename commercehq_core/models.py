from django.db import models
from django.contrib.auth.models import User

import textwrap
from urlparse import urlparse


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
    class Meta:
        ordering = ['-created_at']

    store = models.ForeignKey('CommerceHQStore', related_name='products')
    user = models.ForeignKey(User)

    data = models.TextField(default='{}', blank=True)
    notes = models.TextField(null=True, blank=True)

    title = models.CharField(max_length=300, db_index=True)
    price = models.FloatField(blank=True, null=True, db_index=True)
    product_type = models.CharField(max_length=300, db_index=True)
    tags = models.TextField(blank=True, default='', db_index=True)
    is_multi = models.BooleanField(default=False)

    parent_product = models.ForeignKey(
        'CommerceHQProduct', on_delete=models.SET_NULL,
        null=True, blank=True, verbose_name='Dupliacte of product')

    source_id = models.BigIntegerField(default=0, null=True, blank=True, db_index=True, verbose_name='CommerceHQ Product ID')
    default_supplier = models.ForeignKey('CommerceHQSupplier', on_delete=models.SET_NULL, null=True, blank=True)

    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()

    def __unicode__(self):
        try:
            title = self.title
            if len(title) > 79:
                return u'{}...'.format(textwrap.wrap(title, width=79)[0])
            elif title:
                return title
            else:
                return u'<CommerceHQProduct: %d>' % self.id
        except:
            return u'<CommerceHQProduct: %d>' % self.id


class CommerceHQSupplier(models.Model):
    store = models.ForeignKey('CommerceHQStore', related_name='suppliers')
    supplier_name = models.CharField(max_length=300)

    def __unicode__(self):
        return self.supplier_name
