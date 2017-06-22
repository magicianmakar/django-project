import textwrap
import urllib
import json
import re

from pusher import Pusher
from woocommerce import API

from django.db import models
from django.contrib.auth.models import User
from django.conf import settings
from django.utils.crypto import get_random_string


def safeStr(v, default=''):
    """ Always return a str object """

    if isinstance(v, basestring):
        return v
    else:
        return default


class WooStore(models.Model):
    class Meta:
        verbose_name = 'WooCommerce Store'

    user = models.ForeignKey(User)
    title = models.CharField(max_length=300, blank=True, default='')
    api_url = models.CharField(max_length=512)
    api_key = models.CharField(max_length=300)
    api_password = models.CharField(max_length=300)

    is_active = models.BooleanField(default=True)
    store_hash = models.CharField(default='', max_length=50, editable=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __unicode__(self):
        return self.title

    @property
    def wcapi(self):
        return API(
            url=self.api_url,
            consumer_key=self.api_key,
            consumer_secret=self.api_password,
            wp_api=True,
            version='wc/v2',
            verify_ssl=not settings.DEBUG,
            timeout=300)

    def save(self, *args, **kwargs):
        if not self.store_hash:
            self.store_hash = get_random_string(32, 'abcdef0123456789')

        super(WooStore, self).save(*args, **kwargs)

    def get_admin_url(self):
        return self.api_url.rstrip('/') + '/wp-admin'

    def get_suppliers(self):
        return self.woosupplier_set.all().order_by('-is_default')

    def set_default_supplier(self, supplier, commit=False):
        self.default_supplier = supplier

        if commit:
            self.save()

        self.get_suppliers().update(is_default=False)

        supplier.is_default = True
        supplier.save()

    def connected_count(self):
        return self.products.exclude(source_id=0).count()

    def saved_count(self):
        return self.products.filter(source_id=0).count()

    def get_short_hash(self):
        return self.store_hash[:8] if self.store_hash else ''

    def pusher_channel(self):
        return 'woo_{}'.format(self.get_short_hash())

    def pusher_trigger(self, event, data):
        if not settings.PUSHER_APP_ID:
            return

        pusher = Pusher(
            app_id=settings.PUSHER_APP_ID,
            key=settings.PUSHER_KEY,
            secret=settings.PUSHER_SECRET)

        pusher.trigger(self.pusher_channel(), event, data)


class WooProduct(models.Model):
    class Meta:
        verbose_name = 'WooCommerce Product'
        ordering = ['-created_at']

    store = models.ForeignKey('WooStore', related_name='products')
    user = models.ForeignKey(User)

    data = models.TextField(default='{}', blank=True)
    notes = models.TextField(null=True, blank=True)

    title = models.CharField(max_length=300, blank=True, db_index=True)
    price = models.FloatField(blank=True, null=True, db_index=True)
    tags = models.TextField(blank=True, default='', db_index=True)

    source_id = models.BigIntegerField(default=0, null=True, blank=True, db_index=True, verbose_name='WooCommerce Product ID')
    default_supplier = models.ForeignKey('WooSupplier', on_delete=models.SET_NULL, null=True, blank=True)

    variants_map = models.TextField(default='', blank=True)

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
                return u'<WooProduct: %d>' % self.id
        except:
            return u'<WooProduct: %d>' % self.id

    @property
    def parsed(self):
        try:
            return json.loads(self.data)
        except:
            return {}

    @property
    def woocommerce_url(self):
        if self.is_connected:
            admin_url = self.store.get_admin_url().rstrip('/')
            return '{}/post.php?post={}&action=edit'.format(admin_url, self.source_id)

        return None

    @property
    def is_connected(self):
        return bool(self.source_id)

    def save(self, *args, **kwargs):
        data = json.loads(self.data)

        self.title = data.get('title', '')
        self.tags = safeStr(data.get('tags', ''))[:1024]

        try:
            self.price = '%.02f' % float(data['price'])
        except:
            self.price = 0.0

        super(WooProduct, self).save(*args, **kwargs)

    def update_data(self, data):
        if type(data) is not dict:
            data = json.loads(data)

        try:
            product_data = json.loads(self.data)
        except:
            product_data = {}

        product_data.update(data)

        self.data = json.dumps(product_data)

    def retrieve(self):
        """ Retrieve product from WooCommerce API """
        if not self.source_id:
            return None

        r = self.store.wcapi.get('products/{}'.format(self.source_id))
        r.raise_for_status()

        product = r.json()
        product['variants'] = self.retrieve_variants()

        return product

    def retrieve_variants(self):
        variants = []
        page = 1
        while page:
            params = urllib.urlencode({'page': page, 'per_page': 100})
            path = 'products/{}/variations?{}'.format(self.source_id, params)
            r = self.store.wcapi.get(path)
            r.raise_for_status()
            fetched_variants = r.json()
            variants.extend(fetched_variants)
            has_next = 'rel="next"' in r.headers.get('link', '')
            page = page + 1 if has_next else 0

        return variants

    def sync(self):
        if not self.source_id:
            return None

        product_data = self.retrieve()
        product_data['tags'] = ','.join([tag['name'] for tag in product_data.get('tags', [])])
        product_data['images'] = [img['src'] for img in product_data.get('images', [])]
        product_data['title'] = product_data.pop('name')
        product_data['compare_at_price'] = product_data.pop('regular_price')
        product_data['published'] = product_data['status'] == 'publish'

        self.update_data(product_data)
        self.save()

        product = json.loads(self.data)

        return product

    def get_suppliers(self):
        return self.woosupplier_set.all().order_by('-is_default')

    def set_default_supplier(self, supplier, commit=False):
        self.default_supplier = supplier

        if commit:
            self.save()

        self.get_suppliers().update(is_default=False)

        supplier.is_default = True
        supplier.save()

    def get_variant_mapping(self, name=None, default=None, for_extension=False, supplier=None, mapping_supplier=False):
        mapping = {}

        try:
            if supplier and supplier.variants_map:
                mapping = json.loads(supplier.variants_map)
            elif self.variants_map:
                mapping = json.loads(self.variants_map)
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

        if for_extension and type(mapping) in [str, unicode]:
            mapping = mapping.split(',')

        return mapping

    def set_variant_mapping(self, mapping, supplier=None, update=False):
        if supplier is None:
            supplier = self.default_supplier

        if update:
            try:
                current = json.loads(supplier.variants_map)
            except:
                current = {}

            for k, v in mapping.items():
                current[k] = v

            mapping = current

        if type(mapping) is not str:
            mapping = json.dumps(mapping)

        if supplier:
            supplier.variants_map = mapping
            supplier.save()
        else:
            self.variants_map = mapping
            self.save()


class WooSupplier(models.Model):
    store = models.ForeignKey('WooStore', related_name='suppliers')
    product = models.ForeignKey('WooProduct')

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
            return u'<WooSupplier: {}>'.format(self.id)

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
