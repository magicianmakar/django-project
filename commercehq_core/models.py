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

    def get_admin_url(self, page=''):
        return self.get_api_url(page, api=False)

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

    config = models.TextField(null=True, blank=True)
    variants_map = models.TextField(default='', blank=True)
    supplier_map = models.TextField(default='', null=True, blank=True)
    shipping_map = models.TextField(default='', null=True, blank=True)
    mapping_config = models.TextField(null=True, blank=True)

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

    @property
    def commercehq_url(self):
        if self.is_connected:
            return '{}?id={}'.format(self.store.get_admin_url('admin/products/view'), self.source_id)
        else:
            return None

    @property
    def is_connected(self):
        return bool(self.source_id)

    def have_supplier(self):
        try:
            return self.default_supplier is not None
        except:
            return False

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

        if commit:
            self.save()

        self.get_suppliers().update(is_default=False)

        supplier.is_default = True
        supplier.save()

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

    def get_mapping_config(self):
        try:
            return json.loads(self.mapping_config)
        except:
            return {}

    def set_mapping_config(self, config):
        if type(config) is not str:
            config = json.dumps(config)

        self.mapping_config = config
        self.save()

    def set_suppliers_mapping(self, mapping):
        if type(mapping) is not str:
            mapping = json.dumps(mapping)

        self.supplier_map = mapping
        self.save()

    def get_suppliers_mapping(self, name=None, default=None):
        mapping = {}
        try:
            if self.supplier_map:
                mapping = json.loads(self.supplier_map)
            else:
                mapping = {}
        except:
            mapping = {}

        if name:
            mapping = mapping.get(str(name), default)

        try:
            mapping = json.loads(mapping)
        except:
            pass

        if type(mapping) is int:
            mapping = str(mapping)

        return mapping

    def get_suppier_for_variant(self, variant_id):
        """
            Return the mapped Supplier for the given variant_id
            or the default one if mapping is not set/found
        """

        config = self.get_mapping_config()
        mapping = self.get_suppliers_mapping(name=variant_id)

        if not variant_id or not mapping or config.get('supplier') == 'default':
            return self.default_supplier

        try:
            return self.productsupplier_set.get(id=mapping['supplier'])
        except:
            return self.default_supplier

    def get_shipping_for_variant(self, supplier_id, variant_id, country_code):
        """ Return Shipping Method for the given variant_id and country_code """
        mapping = self.get_shipping_mapping(supplier=supplier_id, variant=variant_id)

        if variant_id and country_code and mapping and type(mapping) is list:
            for method in mapping:
                if country_code == method.get('country'):
                    short_name = method.get('method_name').split(' ')
                    if len(short_name) > 1 and short_name[1].lower() in ['post', 'seller\'s', 'aliexpress']:
                        method['method_short'] = ' '.join(short_name[:2])
                    else:
                        method['method_short'] = short_name[0]

                    if method['country'] == 'GB':
                        method['country'] = 'UK'

                    return method

        return None

    def set_shipping_mapping(self, mapping, update=True):
        if update:
            try:
                current = json.loads(self.shipping_map)
            except:
                current = {}

            for k, v in mapping.items():
                current[k] = v

            mapping = current

        if type(mapping) is not str:
            mapping = json.dumps(mapping)

        self.shipping_map = mapping
        self.save()

    def get_shipping_mapping(self, supplier=None, variant=None, default=None):
        mapping = {}
        try:
            if self.shipping_map:
                mapping = json.loads(self.shipping_map)
            else:
                mapping = {}
        except:
            mapping = {}

        if supplier and variant:
            mapping = mapping.get('{}_{}'.format(supplier, variant), default)

        try:
            mapping = json.loads(mapping)
        except:
            pass

        if type(mapping) is int:
            mapping = str(mapping)

        return mapping


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

    def get_source_id(self):
        try:
            if 'aliexpress.com' in self.product_url.lower():
                return int(re.findall('[/_]([0-9]+).html', self.product_url)[0])
        except:
            return None

    def get_store_id(self):
        try:
            if 'aliexpress.com' in self.supplier_url.lower():
                return int(re.findall('/([0-9]+)', self.supplier_url).pop())
        except:
            return None

    def short_product_url(self):
        source_id = self.get_source_id()
        if source_id:
            if 'aliexpress.com' in self.product_url.lower():
                return u'https://www.aliexpress.com/item//{}.html'.format(source_id)

        return self.product_url

    def support_auto_fulfill(self):
        """
        Return True if this supplier support auto fulfill using the extension
        Currently only Aliexpress support that
        """

        return 'aliexpress.com/' in self.product_url.lower()

    def get_name(self):
        if self.supplier_name and self.supplier_name.strip():
            name = self.supplier_name.strip()
        else:
            supplier_idx = 1
            for i in self.product.get_suppliers():
                if self.id == i.id:
                    break
                else:
                    supplier_idx += 1

            name = u'Supplier #{}'.format(supplier_idx)

        return name


class CommerceHQBoard(models.Model):
    class Meta:
        verbose_name = "CHQ Board"
        verbose_name_plural = "CHQ Boards"

    user = models.ForeignKey(User)
    title = models.CharField(max_length=512)

    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Submission date')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Last update')

    def __unicode__(self):
        return self.title

