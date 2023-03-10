import json
import re
from math import ceil

from urllib.parse import urlparse

from requests import Session
from pusher import Pusher

from django.db import models
from django.db.models import Q
from django.conf import settings
from django.contrib.auth.models import User
from django.utils.crypto import get_random_string
from django.utils.functional import cached_property
from lib.exceptions import capture_exception

from product_alerts.utils import monitor_product
from shopified_core.decorators import add_to_class
from shopified_core.models import StoreBase, ProductBase, SupplierBase, BoardBase, OrderTrackBase, UserUploadBase
from shopified_core.utils import (
    get_domain,
    safe_str,
    dict_val,
    safe_int,
)


@add_to_class(User, 'get_gkart_boards')
def user_get_gkart_boards(self):
    if self.is_subuser:
        return self.profile.subuser_parent.get_gkart_boards()
    else:
        return self.groovekartboard_set.all().order_by('title')


class GrooveKartStoreSession(Session):
    def __init__(self, store):
        self._store = store
        super().__init__()

    def post(self, *args, **kwargs):
        kwargs = self.update_json_data(kwargs)
        return super().post(*args, **kwargs)

    def update_json_data(self, kwargs):
        if not kwargs.get('json'):
            kwargs['json'] = {}

        auth_token, api_key = self._store.api_token, self._store.api_key
        kwargs['json'].update({
            'auth_token': auth_token,
            'api_key': api_key,
            'api_user': 'dropified',
        })

        return kwargs


class GrooveKartStore(StoreBase):
    class Meta(StoreBase.Meta):
        verbose_name = 'GrooveKart Store'

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    title = models.CharField(max_length=300, blank=True, default='')
    api_url = models.CharField(max_length=512, blank=True, default='')
    api_key = models.CharField(max_length=300, blank=True, default='')
    api_token = models.CharField(max_length=300, blank=True, default='')
    is_active = models.BooleanField(default=True)
    store_hash = models.CharField(default='', max_length=50, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_lite = models.BooleanField(default=False)

    def __str__(self):
        return self.title

    @property
    def request(self):
        return GrooveKartStoreSession(self)

    def save(self, *args, **kwargs):
        if not self.store_hash:
            self.store_hash = get_random_string(32, 'abcdef0123456789')

        super().save(*args, **kwargs)

    def get_store_url(self):
        return self.api_url.rstrip('/')

    def get_admin_url(self):
        return f'{self.get_store_url()}/administration'

    def get_admin_order_details(self, order_id):
        return f'{self.get_admin_url()}/v2/index.php?controller=AdminOrders&id_order={order_id}&vieworder'

    def get_api_url(self, path):
        return '{}/api/{}'.format(self.get_store_url(), path.lstrip('/'))

    def get_short_hash(self):
        return self.store_hash[:8] if self.store_hash else ''

    def pusher_channel(self):
        return 'gkart_{}'.format(self.get_short_hash())

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

    def get_groovekart_products(self, limit=False):
        """Return groovekart API products

        :param limit: False or int
        """
        products = []
        chunk = 50
        page = 1

        if limit is not False:
            max_pages = ceil(limit / chunk)
            if limit < chunk:
                chunk = limit

        api_url = self.get_api_url('list_products.json')

        while True:
            params = {
                'offset': chunk * (page - 1),
                'limit': chunk,
                'only_active': True
            }
            r = self.request.post(api_url, json=params)
            result = r.json()

            if r.ok:
                if 'Error' in result:
                    return products

                products += result['products']
                if max_pages is not False and page >= max_pages:
                    return products

                page += 1

            r.raise_for_status()

    def get_order(self, order_id):
        api_url = self.get_api_url('orders.json')
        r = self.request.post(api_url, json={
            'order_id': safe_int(order_id),
        })
        r.raise_for_status()

        order = r.json()
        order['order_number'] = order['id']
        for line in order['line_items']:
            variant_id = line['variants']['variant_id']
            if variant_id == 0:
                line['variant_id'] = -1
            else:
                line['variant_id'] = variant_id
            line['title'] = line['name']

        from groovekart_core.utils import gkart_customer_address
        order['shipping_address'] = gkart_customer_address(
            order,
            shipstation_fix=True
        )
        return order

    def get_product(self, product_id, store):
        return GrooveKartProduct.objects.get(source_id=product_id, store=store)


class GrooveKartProduct(ProductBase):
    class Meta(ProductBase.Meta):
        verbose_name = 'GrooveKart Product'
        ordering = ['-created_at']

    store = models.ForeignKey('GrooveKartStore', related_name='products', null=True, on_delete=models.CASCADE)

    source_id = models.BigIntegerField(default=0, null=True, blank=True, db_index=True, verbose_name='GrooveKartSupplier Product ID')
    source_slug = models.CharField(max_length=300, blank=True, default='')
    default_supplier = models.ForeignKey('GrooveKartSupplier', on_delete=models.SET_NULL, null=True, blank=True)

    parent_product = models.ForeignKey('GrooveKartProduct', on_delete=models.SET_NULL, null=True, blank=True, verbose_name='Duplicate of product')

    def __str__(self):
        return f'<GrooveKartProduct: {self.id}>'

    @staticmethod
    def get_variant_options(variant):
        description = variant.get('description') or ''
        return description.split(' | ')

    @property
    def parsed(self):
        try:
            data = json.loads(self.data)

            if type(data['images']) is dict:
                data['images'] = list(data['images'].values())

            if self.source_id:
                data['images'] = list([self.get_large_image_url(i) for i in data.get('images', [])])

                if data.get('cover_image'):
                    data['cover_image'] = self.get_large_image_url(data['cover_image'])

            return data

        except:
            return {}

    @property
    def groovekart_url(self):
        if self.is_connected:
            admin_url = self.store.get_admin_url().rstrip('/')
            return '{}/v2/index.php/product/form/{}'.format(admin_url, self.source_id)

    @property
    def is_connected(self):
        return bool(self.source_id)

    def get_images(self):
        try:
            return self.parsed['images']
        except:
            return []

    def have_supplier(self):
        try:
            return self.default_supplier is not None
        except:
            return False

    def get_large_image_url(self, image):
        if image:
            image = image.replace('-large_default2x', '')

            # Matches: "945.jpg?v=1571331426" or "945.jpg"
            return re.sub(r'(\d+)(\.\w+(\?v=\S+)?)$', r'\1-large_default\2', image)

        return image

    def get_gkart_id(self):
        return self.source_id if self.store else None

    def save(self, *args, **kwargs):
        data = json.loads(self.data)

        self.title = data.get('title', '')
        self.tags = safe_str(data.get('tags', ''))[:1024]
        self.product_type = safe_str(data.get('type', ''))[:254]

        try:
            self.price = '%.02f' % float(data['price'])
        except:
            self.price = 0.0

        super().save(*args, **kwargs)

    def sync(self):
        product_data = self.retrieve(attempts=2)
        product_variants = product_data.get('variants', [])
        self.update_data({'title': product_data.get('title', product_data.get('product_title'))})
        self.update_data({'price': f'{float(product_data["price"]):,.2f}'})
        self.update_data({'compare_at_price': f'{float(product_data["compare_default_price"]):,.2f}'})
        self.update_data({'weight': product_data['weight']})
        self.update_data({'sku': product_data['sku']})
        self.update_data({'description': product_data['description']})
        self.update_data({'cover_image': product_data.get('cover_image', '')})
        self.update_data({'tags': product_data.get('tags', '')})
        self.update_data({'vendor': product_data.get('manufacturer_name', '')})
        self.update_data({'type': safe_int(product_data['id_category_default'])})
        self.update_data({'variants': self.sync_variants(product_variants)})
        self.update_data({'images': {i.get('id'): i.get('url') for i in product_data.get('images', [])}})
        self.save()

        return self.parsed

    def sync_variants(self, product_variants):
        variants = []
        variant_options = {}

        for product_variant in product_variants:
            variant_id = dict_val(product_variant, ['id_product_attribute', 'id_product_variant'])
            variant_name = dict_val(product_variant, ['attribute_name', 'variant_name'])
            variant_options.setdefault(product_variant['group_name'], set()).add(variant_name)
            product_variant['price'] = "%.2f" % float(product_variant['price'])
            product_variant['compare_at_price'] = "%.2f" % float(product_variant['compare_price'])

            for variant in variants:
                if variant_id == variant['id']:
                    variant['description'] += ' | {}'.format(variant_name)
                    break
            else:
                product_variant['id'] = variant_id
                product_variant['description'] = variant_name
                if product_variant.get('image'):
                    src = product_variant['image']['url']
                    m = re.search(r'\?', src)
                    src = src[:m.span()[0]] if m else src
                    results = re.findall(r'(\.jpg)|(\.jpeg)|(\.png)', src)
                    extension = results.pop()[0] if results else ''
                    file = src.rstrip(extension)
                    product_variant['image']['src'] = "{}-small_default{}".format(file, extension)
                variants.append(product_variant)

        if not variants:
            variants = [{'id': -1, 'description': 'Default Title'}]

        variant_options = [{'title': title, 'values': list(values)} for title, values in variant_options.items()]
        self.update_data({'variant_options': variant_options})

        return variants

    def retrieve(self, attempts=1):
        # TODO: Change URL to products.json when it start returning Vendor/Manufacturer Name
        endpoint = self.store.get_api_url('search_products.json')
        json_data = {'ids': self.source_id}

        for _ in reversed(range(attempts)):
            try:
                r = self.store.request.post(endpoint, json=json_data)
                r.raise_for_status()
                product_data = r.json()['products']['0']

                for variant in product_data['variants']:
                    if variant['default_on'] == '1':
                        product_data['price'] = variant['price']

                return product_data

            except:
                if attempts > 0:
                    continue

                capture_exception()
                raise

    def get_config(self):
        try:
            return json.loads(self.config)
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

    def get_suppliers(self):
        return self.groovekartsupplier_set.all().order_by('-is_default')

    def set_default_supplier(self, supplier, commit=False):
        self.default_supplier = supplier

        if commit:
            self.save()

        self.get_suppliers().update(is_default=False)

        supplier.is_default = True
        supplier.save()

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

    def get_supplier_for_variant(self, variant_id):
        config = self.get_mapping_config()
        mapping = self.get_suppliers_mapping(name=variant_id)

        if not variant_id or not mapping or config.get('supplier') == 'default':
            return self.default_supplier

        try:
            return self.groovekartsupplier_set.get(id=mapping['supplier'])
        except:
            return self.default_supplier

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
        variant_id = -1 if variant_id == 0 else variant_id  # Default variant use -1 as id
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

    def get_image(self):
        return self.parsed.get('cover_image', '')

    def get_cover_image_id(self):
        image_id = re.findall(r'\/(\d+)\-large', self.parsed.get('cover_image', ''))
        return image_id[0] if image_id else None

    def get_original_info(self):
        if self.have_supplier():
            url = self.default_supplier.product_url

            try:
                domain = urlparse(url).hostname
            except:
                domain = None

            if domain is None:
                return domain

            for i in ['com', 'co.uk', 'org', 'net']:
                domain = domain.replace('.%s' % i, '')

            domain = domain.split('.')[-1]
            source = {
                'aliexpress': 'AliExpress',
                'ebay': 'eBay',
            }.get(domain.lower(), domain.title())

            return {
                'domain': domain,
                'source': source,
                'url': url
            }

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
                    options = GrooveKartProduct.get_variant_options(v)
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

    def get_master_variants_map(self):
        try:
            return json.loads(self.master_variants_map)
        except:
            return {}

    def set_master_variants_map(self, mapping):
        if type(mapping) is not str:
            mapping = json.dumps(mapping)

        self.master_variants_map = mapping
        self.save()


class GrooveKartSupplier(SupplierBase):
    store = models.ForeignKey('GrooveKartStore', null=True, related_name='suppliers', on_delete=models.CASCADE)
    product = models.ForeignKey('GrooveKartProduct', on_delete=models.CASCADE)

    product_url = models.CharField(max_length=512, null=True, blank=True)
    supplier_name = models.CharField(max_length=512, null=True, blank=True, db_index=True)
    supplier_url = models.CharField(max_length=512, null=True, blank=True)
    shipping_method = models.CharField(max_length=512, null=True, blank=True)
    variants_map = models.TextField(null=True, blank=True)
    is_default = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'<GrooveKartSupplier: {self.id}>'

    def get_source_id(self):
        try:
            if self.is_aliexpress or self.is_alibaba:
                return int(re.findall('[/_]([0-9]+).html', self.product_url)[0])
            elif self.is_ebay:
                return int(re.findall(r'ebay\.[^/]+\/itm\/(?:[^/]+\/)?([0-9]+)', self.product_url)[0])
            elif self.is_dropified_print:
                return int(re.findall(r'print-on-demand.+?([0-9]+)', self.product_url)[0])
            elif self.is_pls:
                return self.get_user_supplement_id()
            elif self.is_logistics:
                return int(re.findall(r'logistics/product/([0-9]+)', self.product_url)[0])
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

    def save(self, *args, **kwargs):
        if self.is_default:
            try:
                if not settings.DEBUG:
                    monitor_product(self.product)
            except:
                pass

        super(GrooveKartSupplier, self).save(*args, **kwargs)


class GrooveKartUserUpload(UserUploadBase):
    product = models.ForeignKey('GrooveKartProduct', null=True, on_delete=models.CASCADE)


class GrooveKartBoard(BoardBase):
    products = models.ManyToManyField('GrooveKartProduct', blank=True, related_name='boards')

    def __str__(self):
        return f'<GrooveKartBoard: {self.id}>'

    def saved_count(self, request=None):
        # Filter non-connected products
        products = self.products.filter(source_id=0)

        if request and request.user.is_subuser:
            # If it's a sub user, only show him products in stores he have access to
            products = products.filter(Q(store__in=request.user.profile.get_gkart_stores()) | Q(store=None))

        else:
            # Show the owner product linked to active stores and products with store set to None
            products = products.filter(Q(store__is_active=True) | Q(store=None))

        return products.count()

    def connected_count(self, request=None):
        # Only get products linked to a Shopify product and with an active store
        products = self.products.filter(store__is_active=True).exclude(source_id=0)

        if request and request.user.is_subuser:
            products = products.filter(store__in=request.user.profile.get_gkart_stores())

        return products.count()


class GrooveKartOrderTrack(OrderTrackBase):
    CUSTOM_TRACKING_KEY = 'gkart_custom_tracking'

    store = models.ForeignKey('GrooveKartStore', null=True, on_delete=models.CASCADE)
    groovekart_status = models.CharField(max_length=128, blank=True, null=True, default='', verbose_name="GrooveKart Fulfillment Status")

    def __str__(self):
        return f'<GrooveKartOrderTrack: {self.id}>'

    @cached_property
    def custom_tracking_url(self):
        custom_tracking = self.user.get_config(self.CUSTOM_TRACKING_KEY)
        if type(custom_tracking) is dict:
            return custom_tracking.get(str(self.store_id))
        return None
