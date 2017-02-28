from django.db import models
from django.conf import settings
from django.contrib.auth.models import User
from django.utils.crypto import get_random_string

import re
import textwrap
import simplejson as json

import requests
from pusher import Pusher


def add_to_class(cls, name):
    def _decorator(*args, **kwargs):
        cls.add_to_class(name, args[0])
    return _decorator


def safeStr(v, default=''):
    """ Always return a str object """

    if isinstance(v, basestring):
        return v
    else:
        return default


class CommerceHQStore(models.Model):
    class Meta:
        verbose_name = 'CHQ Store'
        ordering = ['-created_at']

    user = models.ForeignKey(settings.AUTH_USER_MODEL)
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

    @property
    def request(self):
        s = requests.Session()
        s.auth = (self.api_key, self.api_password)
        return s

    def connected_count(self):
        return self.products.exclude(source_id=0).count()

    def saved_count(self):
        return self.products.filter(source_id=0).count()

    def get_short_hash(self):
        return self.store_hash[:8] if self.store_hash else ''

    def pusher_channel(self):
        return 'chq_{}'.format(self.get_short_hash())

    def pusher_trigger(self, event, data):
        if not settings.PUSHER_APP_ID:
            return

        pusher = Pusher(
            app_id=settings.PUSHER_APP_ID,
            key=settings.PUSHER_KEY,
            secret=settings.PUSHER_SECRET)

        pusher.trigger(self.pusher_channel(), event, data)


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

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

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

    def save(self, *args, **kwargs):
        data = json.loads(self.data)

        self.title = data.get('title', '')
        self.tag = safeStr(data.get('tags', ''))[:1024]
        self.product_type = safeStr(data.get('type', ''))[:254]

        try:
            self.price = '%.02f' % float(data['price'])
        except:
            self.price = 0.0

        super(CommerceHQProduct, self).save(*args, **kwargs)

    @property
    def parsed(self):
        try:
            return json.loads(self.data)
        except:
            return {}

    def update_data(self, data):
        if type(data) is not dict:
            data = json.loads(data)

        try:
            product_data = json.loads(self.data)
        except:
            product_data = {}

        product_data.update(data)

        self.data = json.dumps(product_data)

    def set_default_supplier(self, supplier, commit=False):
        self.default_supplier = supplier

        print self.get_suppliers().values('is_default'), '=>', self.default_supplier

        if commit:
            self.save()

        self.get_suppliers().update(is_default=False)

        supplier.is_default = True
        supplier.save()
        print self.get_suppliers().values('is_default'), '=>', self.default_supplier

    def get_suppliers(self):
        return self.commercehqsupplier_set.all().order_by('-is_default')

    def retrieve(self):
        """ Retrieve product from CommerceHQ API """

        if not self.source_id:
            return None

        rep = self.store.request.get(
            url='{}/{}'.format(self.store.get_api_url('products'), self.source_id),
            params={
                'expand': 'variants,options,images,textareas'
            }
        )

        if rep.ok:
            return rep.json()

    def sync(self):
        product = self.retrieve()
        if not product:
            return None

        product['tags'] = ','.join(product['tags']) if type(product['tags']) is list else ''

        for idx, img in enumerate(product['images']):
            print idx, img
            product['images'][idx] = img['path']

        for i in product['textareas']:
            if i['name'] == 'Description':
                product['description'] = i['text']

        product['compare_at_price'] = product.get('compare_price')
        product['weight'] = product['shipping_weight']
        product['published'] = not product['is_draft']
        product['textareas'] = []

        self.update_data(product)
        self.save()

        return json.loads(self.data)


class CommerceHQSupplier(models.Model):
    store = models.ForeignKey(CommerceHQStore, related_name='suppliers')
    product = models.ForeignKey(CommerceHQProduct)

    product_url = models.CharField(max_length=512, null=True, blank=True)
    supplier_name = models.CharField(max_length=512, null=True, blank=True, db_index=True)
    supplier_url = models.CharField(max_length=512, null=True, blank=True)
    shipping_method = models.CharField(max_length=512, null=True, blank=True)
    variants_map = models.TextField(null=True, blank=True)
    is_default = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __unicode__(self):
        if self.supplier_name:
            return self.supplier_name
        elif self.supplier_url:
            return self.supplier_url
        else:
            return u'<CommerceHQSupplier: {}>'.format(self.id)
