import requests
import json
import re

from pusher import Pusher

from django.db import models
from django.utils.functional import cached_property
from django.conf import settings
from django.contrib.auth.models import User
from django.utils.crypto import get_random_string
from django.urls import reverse

from shopified_core.utils import get_domain, safe_str
from shopified_core.decorators import add_to_class
from shopified_core.models import StoreBase, ProductBase, SupplierBase, BoardBase, OrderTrackBase, UserUploadBase


@add_to_class(User, 'get_gear_boards')
def user_get_gear_boards(self):
    if self.is_subuser:
        return self.profile.subuser_parent.get_gear_boards()
    else:
        return self.gearbubbleboard_set.all().order_by('title')


class GearBubbleStore(StoreBase):
    class Meta(StoreBase.Meta):
        verbose_name = 'GearBubble Store'

    STAGING = 'staging'
    LIVE = 'live'
    MODE_CHOICES = [(STAGING, 'Staging'), (LIVE, 'Live')]

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    title = models.CharField(max_length=300, blank=True, default='')
    api_token = models.CharField(max_length=300)
    is_active = models.BooleanField(default=True)
    store_hash = models.CharField(default='', max_length=50, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    mode = models.CharField(max_length=7, choices=MODE_CHOICES, default=LIVE)

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.store_hash:
            self.store_hash = get_random_string(32, 'abcdef0123456789')

        super(GearBubbleStore, self).save(*args, **kwargs)

    @cached_property
    def request(self):
        session = requests.Session()
        session.headers.update({'Authorization': 'Token token={}'.format(self.api_token)})

        return session

    def get_api_url(self, path):
        return '{}/api/v1/{}'.format(self.get_store_url(), path.rstrip('/'))

    def get_store_url(self):
        return settings.GEARBUBBLE_STAGING_URL if self.mode == 'staging' else settings.GEARBUBBLE_LIVE_URL

    def get_admin_url(self):
        return '{}/{}'.format(self.get_store_url(), 'pro_dashboard')

    def get_short_hash(self):
        return self.store_hash[:8] if self.store_hash else ''

    def pusher_channel(self):
        return 'gear_{}'.format(self.get_short_hash())

    def pusher_trigger(self, event, data):
        if not settings.PUSHER_APP_ID:
            return

        pusher = Pusher(
            app_id=settings.PUSHER_APP_ID,
            key=settings.PUSHER_KEY,
            secret=settings.PUSHER_SECRET)

        pusher.trigger(self.pusher_channel(), event, data)

    def saved_count(self):
        return self.products.filter(source_id=0).count()

    def connected_count(self):
        return self.products.exclude(source_id=0).count()

    def get_gearbubble_products(self):
        products = []
        params = {'page': 1, 'limit': 50}

        while params['page']:
            api_url = self.get_api_url('private_products')
            r = self.request.get(api_url, params=params)

            if r.ok:
                products += r.json()['products']
                params['page'] += 1

            if r.status_code == 404:
                return products

            r.raise_for_status()


class GearBubbleProduct(ProductBase):
    class Meta(ProductBase.Meta):
        verbose_name = 'GearBubble Product'
        ordering = ['-created_at']

    store = models.ForeignKey('GearBubbleStore', related_name='products', null=True, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)

    data = models.TextField(default='{}', blank=True)
    notes = models.TextField(null=True, blank=True)

    title = models.CharField(max_length=300, blank=True, db_index=True)
    price = models.FloatField(blank=True, null=True, db_index=True)
    tags = models.TextField(blank=True, default='', db_index=True)
    product_type = models.CharField(max_length=300, blank=True, default='', db_index=True)

    source_id = models.BigIntegerField(default=0, null=True, blank=True, db_index=True, verbose_name='GearBubble Product ID')
    source_slug = models.CharField(max_length=300, blank=True, default='')
    default_supplier = models.ForeignKey('GearBubbleSupplier', on_delete=models.SET_NULL, null=True, blank=True)

    variants_map = models.TextField(default='', blank=True)
    supplier_map = models.TextField(default='', null=True, blank=True)
    shipping_map = models.TextField(default='', null=True, blank=True)
    mapping_config = models.TextField(null=True, blank=True)

    parent_product = models.ForeignKey('GearBubbleProduct', on_delete=models.SET_NULL, null=True, blank=True, verbose_name='Duplicate of product')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @staticmethod
    def update_variant_properties(product_data):
        images = product_data.get('images', [])
        images_by_id = {image['id']: image for image in images}

        for variant in product_data.get('variants', []):
            options = GearBubbleProduct.get_variant_options(variant)
            variant['options'] = options
            variant['description'] = ', '.join(options)
            variant['image'] = images_by_id.get(variant['image_id'], {})

        return product_data

    @staticmethod
    def get_variant_options(variant):
        options, option_number = [], 1

        while True:
            option = variant.get('option{}'.format(option_number))
            if option is not None:
                options.append(option)
                option_number += 1
                continue
            break

        return options

    def __str__(self):
        return f'<GearBubbleProduct: {self.id}>'

    @property
    def parsed(self):
        try:
            return json.loads(self.data)
        except:
            return {}

    @property
    def gearbubble_url(self):
        if self.is_connected:
            path = 'private_products/{}/edit'.format(self.source_id)
            return '{}/{}'.format(self.store.get_store_url(), path)

        return None

    @property
    def is_connected(self):
        return bool(self.source_id)

    @property
    def boards(self):
        return self.gearbubbleboard_set

    @property
    def has_supplier(self):
        try:
            return self.default_supplier is not None
        except:
            return False

    @property
    def variant_edit(self):
        if self.is_connected:
            return reverse('gear:variants_edit', args=(self.store.id, self.source_id))

        return None

    def save(self, *args, **kwargs):
        data = json.loads(self.data)

        self.title = data.get('title', '')
        self.tags = safe_str(data.get('tags', ''))[:1024]
        self.product_type = safe_str(data.get('type', ''))[:254]

        try:
            self.price = '%.02f' % float(data['price'])
        except:
            self.price = 0.0

        super(GearBubbleProduct, self).save(*args, **kwargs)

    def update_data(self, data):
        if type(data) is not dict:
            data = json.loads(data)

        try:
            product_data = json.loads(self.data)
        except:
            product_data = {}

        product_data.update(data)

        self.data = json.dumps(product_data)

    def get_suppliers(self):
        return self.gearbubblesupplier_set.all().order_by('-is_default')

    def set_default_supplier(self, supplier, commit=False):
        self.default_supplier = supplier

        if commit:
            self.save()

        self.get_suppliers().update(is_default=False)

        supplier.is_default = True
        supplier.save()

    def retrieve(self):
        if not self.source_id:
            raise ValueError('The product is not connected to a store.')

        url = self.store.get_api_url('private_products/{}'.format(self.source_id))
        r = self.store.request.get(url)
        r.raise_for_status()

        return r.json()['product']

    def get_product_data(self):
        product_data = self.retrieve()
        product_data = GearBubbleProduct.update_variant_properties(product_data)

        return product_data

    def sync(self):
        product_data = self.get_product_data()
        images = product_data.get('images', [])
        images = [img['src'] for img in images if not img['variant_id']]

        self.update_data({'images': images})
        self.update_data({'title': product_data['title']})
        self.update_data({'description': product_data['body_html']})
        self.update_data({'tags': product_data['tags']})
        self.update_data({'variants': product_data.get('variants', [])})
        self.update_data({'options': product_data.get('options', [])})
        self.update_data({'source_id': product_data['id']})
        self.update_data({'source_slug': product_data['slug']})

        if 'price' in product_data:
            self.update_data({'price': product_data['price']})

        if 'compare_at_price' in product_data:
            self.update_data({'compare_at_price': product_data['compare_at_price']})

        if 'available_qty' in product_data:
            self.update_data({'available_qty': product_data['available_qty']})

        if 'weight' in product_data:
            self.update_data({'weight': product_data['weight']})

        if 'weight_unit' in product_data:
            self.update_data({'weight_unit': product_data['weight_unit']})

        self.save()

        return self.parsed

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

    def get_variant_mapping(self, name=None, default=None, for_extension=False, supplier=None, mapping_supplier=False):
        mapping = {}

        if supplier is None:
            if mapping_supplier:
                supplier = self.get_supplier_for_variant(name)
            else:
                supplier = self.default_supplier

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

        if for_extension and mapping:
            if name:
                if type(mapping) is str:
                    mapping = mapping.split(',')
            else:
                for k, v in list(mapping.items()):
                    m = str(v) if type(v) is int else v

                    try:
                        m = json.loads(v)
                    except:
                        if type(v) is str:
                            m = v.split(',')

                    mapping[k] = m

        return mapping

    def set_variant_mapping(self, mapping, supplier=None, update=False, commit=True):
        if supplier is None:
            supplier = self.default_supplier

        if update:
            try:
                current = json.loads(supplier.variants_map)
            except:
                current = {}

            for k, v in list(mapping.items()):
                current[k] = v

            mapping = current

        if type(mapping) is not str:
            mapping = json.dumps(mapping)

        if supplier:
            supplier.variants_map = mapping
            if commit:
                supplier.save()
        else:
            self.variants_map = mapping
            if commit:
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

    def set_suppliers_mapping(self, mapping, commit=True):
        if type(mapping) is not str:
            mapping = json.dumps(mapping)

        self.supplier_map = mapping

        if commit:
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

    def set_shipping_mapping(self, mapping, update=True, commit=True):
        if update:
            try:
                current = json.loads(self.shipping_map)
            except:
                current = {}

            for k, v in list(mapping.items()):
                current[k] = v

            mapping = current

        if type(mapping) is not str:
            mapping = json.dumps(mapping)

        self.shipping_map = mapping

        if commit:
            self.save()

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

    def get_all_variants_mapping(self):
        all_mapping = {}

        product = self.sync()
        if not product:
            return None

        for supplier in self.get_suppliers():
            variants_map = self.get_variant_mapping(supplier=supplier)

            seen_variants = []
            for i, v in enumerate(product['variants']):
                mapped = variants_map.get(str(v['id']))
                if mapped:
                    options = mapped
                else:
                    options = v['options']

                    options = [{'title': a} for a in options]

                try:
                    if type(options) not in [list, dict]:
                        options = json.loads(options)

                        if type(options) is int:
                            options = str(options)
                except:
                    pass

                variants_map[str(v['id'])] = options
                seen_variants.append(str(v['id']))

            for k in list(variants_map.keys()):
                if k not in seen_variants:
                    del variants_map[k]

            all_mapping[str(supplier.id)] = variants_map

        return all_mapping


class GearBubbleSupplier(SupplierBase):
    store = models.ForeignKey('GearBubbleStore', null=True, related_name='suppliers', on_delete=models.CASCADE)
    product = models.ForeignKey('GearBubbleProduct', on_delete=models.CASCADE)

    product_url = models.CharField(max_length=512, null=True, blank=True)
    supplier_name = models.CharField(max_length=512, null=True, blank=True, db_index=True)
    supplier_url = models.CharField(max_length=512, null=True, blank=True)
    shipping_method = models.CharField(max_length=512, null=True, blank=True)
    variants_map = models.TextField(null=True, blank=True)
    is_default = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'<GearBubbleSupplier: {self.id}>'

    def get_source_id(self):
        try:
            if self.is_aliexpress:
                return int(re.findall('[/_]([0-9]+).html', self.product_url)[0])
            elif self.is_ebay:
                return int(re.findall(r'ebay\.[^/]+\/itm\/(?:[^/]+\/)?([0-9]+)', self.product_url)[0])
        except:
            return None

    def get_store_id(self):
        try:
            if self.is_aliexpress:
                return int(re.findall('/([0-9]+)', self.supplier_url).pop())
        except:
            return None

    def short_product_url(self):
        source_id = self.get_source_id()
        if source_id:
            if self.is_aliexpress:
                return 'https://www.aliexpress.com/item/{}.html'.format(source_id)
            if self.is_ebay:
                return 'https://www.ebay.com/itm/{}'.format(source_id)

        return self.product_url

    def support_auto_fulfill(self):
        """
        Return True if this supplier support auto fulfill using the extension
        Currently Aliexpress and eBay (US) support that
        """

        return self.is_aliexpress or self.is_ebay_us

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

            name = 'Supplier {}#{}'.format(self.supplier_type(), supplier_idx)

        return name

    def supplier_type(self):
        try:
            return get_domain(self.product_url)
        except:
            return ''

    @property
    def is_aliexpress(self):
        return self.supplier_type() == 'aliexpress'

    @property
    def is_ebay(self):
        return self.supplier_type() == 'ebay'

    @property
    def is_ebay_us(self):
        try:
            return 'ebay.com' in get_domain(self.product_url, full=True)
        except:
            return False


class GearUserUpload(UserUploadBase):
    product = models.ForeignKey('GearBubbleProduct', null=True, on_delete=models.CASCADE)


class GearBubbleBoard(BoardBase):
    products = models.ManyToManyField('GearBubbleProduct', blank=True)

    def __str__(self):
        return f'<GearBubbleBoard: {self.id}>'


class GearBubbleOrderTrack(OrderTrackBase):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    store = models.ForeignKey('GearBubbleStore', null=True, on_delete=models.CASCADE)
    gearbubble_status = models.CharField(max_length=128, blank=True, null=True, default='', verbose_name="GearBubble Fulfillment Status")

    def __str__(self):
        return f'<GearBubbleOrderTrack: {self.id}>'
