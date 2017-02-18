from django.db import models
from django.contrib.auth.models import User
from django.utils.crypto import get_random_string

import re
import textwrap
from urlparse import urlparse


def add_to_class(cls, name):
    def _decorator(*args, **kwargs):
        cls.add_to_class(name, args[0])
    return _decorator


class CommerceHQStore(models.Model):
    class Meta:
        verbose_name = 'CHQ Store'
        ordering = ['-created_at']

    user = models.ForeignKey(User)

    title = models.CharField(max_length=300, blank=True, default='')
    api_url = models.CharField(max_length=512)
    api_key = models.CharField(max_length=300)
    api_password = models.CharField(max_length=300)

    is_active = models.BooleanField(default=True)
    store_hash = models.CharField(unique=True, default='', max_length=50, editable=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __unicode__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.store_hash:
            self.store_hash = get_random_string(32, 'abcdef0123456789')

        super(CommerceHQStore, self).save(*args, **kwargs)

    def get_api_url(self, page='', api=True):
        url = re.findall('([^/\.]+\.commercehq(dev:?)?.com)', self.api_url).pop()[0]

        page = page.lstrip('/')
        if api and not page.startswith('api'):
            page = 'api/v1/{}'.format(page).rstrip('/')

        url = 'https://{}/{}'.format(url, page.lstrip('/'))

        return url


class CommerceHQProduct(models.Model):
    class Meta:
        verbose_name = 'CHQ Product'
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
