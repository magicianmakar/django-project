import json
import re
import arrow
from urllib.parse import urlencode, urlparse

from pusher import Pusher
from woocommerce import API

from django.db import models
from django.db.models import Q
from django.contrib.auth.models import User
from django.conf import settings
from django.utils.crypto import get_random_string
from django.urls import reverse

from shopified_core.utils import (
    get_domain,
    safe_str,
)
from shopified_core.decorators import add_to_class
from shopified_core.models import StoreBase, ProductBase, SupplierBase, BoardBase, OrderTrackBase, UserUploadBase, OrdersSyncStatusAbstract

from .mixins import WooAPIDataMixin


@add_to_class(User, 'get_woo_boards')
def user_get_woo_boards(self):
    if self.is_subuser:
        return self.profile.subuser_parent.get_woo_boards()
    else:
        return self.wooboard_set.all().order_by('title')


class WooStore(StoreBase):
    class Meta(StoreBase.Meta):
        verbose_name = 'WooCommerce Store'

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    title = models.CharField(max_length=300, blank=True, default='')
    api_url = models.CharField(max_length=512)
    api_key = models.CharField(max_length=300)
    api_password = models.CharField(max_length=300)

    api_version = models.CharField(max_length=50, default='wc/v2')
    api_string_auth = models.BooleanField(default=True)
    api_timeout = models.IntegerField(default=30)

    is_active = models.BooleanField(default=True)
    store_hash = models.CharField(default='', max_length=50, editable=False)

    auto_fulfill = models.CharField(max_length=50, null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title

    def get_wcapi(self, timeout=30, version=None):
        version = self.api_version if version is None else version
        api_string_auth = self.api_string_auth
        api_timeout = max(self.api_timeout, timeout)

        return API(
            url=self.api_url,
            consumer_key=self.api_key,
            consumer_secret=self.api_password,
            wp_api=True,
            version=version,
            verify_ssl=False,
            query_string_auth=api_string_auth,
            timeout=api_timeout)

    wcapi = property(get_wcapi)

    def save(self, *args, **kwargs):
        if not self.store_hash:
            self.store_hash = get_random_string(32, 'abcdef0123456789')

        try:
            self.auto_fulfill = self.user.get_config('auto_shopify_fulfill', 'enable')
        except User.DoesNotExist:
            pass

        super(WooStore, self).save(*args, **kwargs)

    def get_store_url(self):
        return self.api_url.rstrip('/')

    def get_admin_url(self):
        return self.get_store_url() + '/wp-admin'

    def get_admin_order_details(self, order_id):
        return f'{self.get_admin_url()}/post.php?post={order_id}&action=edit'

    def get_authorize_url(self, params, url=None):
        if not url:
            url = self.get_store_url()

        return '{}/wc-auth/v1/authorize?{}'.format(url.rstrip('/'), urlencode(params))

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

    def get_order(self, order_id):
        wcapi = self.get_wcapi()
        order = wcapi.get(f'orders/{order_id}').json()
        order['order_number'] = order.pop('number')
        order['created_at'] = order.pop('date_created')

        from woocommerce_core.utils import woo_customer_address
        get_config = self.user.models_user.get_config
        order['shipping_address'] = woo_customer_address(
            order,
            german_umlauts=get_config('_use_german_umlauts', False),
            shipstation_fix=True
        )[1]

        for item in order['line_items']:
            item['title'] = item.pop('name')
            if item['variation_id'] == 0:
                item['variation_id'] = item['variant_id'] = -1

        return order

    def get_product(self, product_id, store):
        return WooProduct.objects.get(source_id=product_id, store=store)

    def get_sync_status(self):
        if not self.sync_statuses.count() == 1:
            return

        return self.sync_statuses.first()

    def enable_sync(self):
        sync = self.get_sync_status()
        sync.sync_status = 2 if sync.sync_status == 5 else sync.sync_status
        sync.save()

    def disable_sync(self):
        sync = self.get_sync_status()
        sync.sync_status = 5 if sync.sync_status == 2 else sync.sync_status
        sync.save()

    def is_synced(self):
        sync = self.get_sync_status()

        return sync.sync_status in [2, 5, 6] if sync else False

    def is_sync_enabled(self):
        sync = self.get_sync_status()

        return sync.sync_status in [2, 6] if sync else False

    def is_store_indexed(self):
        sync = self.get_sync_status()

        return sync.sync_status in [2, 6] and sync.elastic if sync else False

    def count_saved_orders(self, days=None):
        orders = self.wooorder_set.all()
        if days:
            orders = orders.filter(date_created__gte=arrow.utcnow().replace(days=-abs(days)).datetime)

        return orders.count()


class WooProduct(ProductBase):
    class Meta(ProductBase.Meta):
        verbose_name = 'WooCommerce Product'
        ordering = ['-created_at']

    store = models.ForeignKey('WooStore', related_name='products', null=True, on_delete=models.CASCADE)

    source_id = models.BigIntegerField(default=0, null=True, blank=True, db_index=True, verbose_name='WooCommerce Product ID')
    default_supplier = models.ForeignKey('WooSupplier', on_delete=models.SET_NULL, null=True, blank=True)

    parent_product = models.ForeignKey('WooProduct', on_delete=models.SET_NULL, null=True, blank=True, verbose_name='Duplicate of product')

    def __str__(self):
        return f'<WooProduct: {self.id}>'

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
    def variant_edit(self):
        if self.is_connected:
            return reverse('woo:variants_edit', args=(self.store.id, self.source_id))

        return None

    @property
    def is_connected(self):
        return bool(self.source_id)

    @property
    def boards(self):
        return self.wooboard_set

    def have_supplier(self):
        try:
            return self.default_supplier is not None
        except:
            return False

    def save(self, *args, **kwargs):
        data = json.loads(self.data)

        self.title = data.get('title', '')
        self.tags = safe_str(data.get('tags', ''))[:1024]
        self.product_type = safe_str(data.get('type', ''))[:254]

        try:
            self.price = '%.02f' % float(data['price'])
        except:
            self.price = 0.0

        super(WooProduct, self).save(*args, **kwargs)

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
            params = {'page': page, 'per_page': 100}
            r = self.store.wcapi.get(f'products/{self.source_id}/variations', params=params)
            r.raise_for_status()
            fetched_variants = r.json()
            variants.extend(fetched_variants)
            has_next = 'rel="next"' in r.headers.get('link', '')
            page = page + 1 if has_next else 0

        for variant in variants:
            attributes = variant.get('attributes', [])
            variant['variant'] = [option['option'] for option in attributes]

        if not variants:
            variants = [{'variant': ['Default Title'], 'id': -1}]

        return variants

    def update_weight_unit(self):
        r = self.store.wcapi.get('settings/products/woocommerce_weight_unit')
        r.raise_for_status()
        self.update_data({'weight_unit': r.json().get('value', '')})

    def get_images(self):
        try:
            return json.loads(self.data)['images']
        except:
            return []

    def get_image(self):
        images = self.get_images()
        return images[0] if images else None

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

    def sync(self):
        if not self.source_id:
            return None

        self.update_weight_unit()

        product_data = self.retrieve()
        product_data['tags'] = self.merge_tags(product_data)
        product_data['images'] = [img['src'] for img in product_data.get('images', [])]
        product_data['title'] = product_data.pop('name')
        product_data['product_type'] = product_data.pop('type')
        product_data['compare_at_price'] = product_data.pop('regular_price')
        product_data['published'] = product_data['status'] == 'publish'

        self.update_data(product_data)
        self.save()

        product = json.loads(self.data)

        return product

    def merge_tags(self, product_data):
        woocommerce_tags = [tag['name'] for tag in product_data.get('tags', [])]
        dropified_tags = self.tags.split(',')

        return ','.join(set(dropified_tags + woocommerce_tags))

    def get_suppliers(self):
        return self.woosupplier_set.all().order_by('-is_default')

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

    def get_supplier_for_variant(self, variant_id):
        """
            Return the mapped Supplier for the given variant_id
            or the default one if mapping is not set/found
        """

        config = self.get_mapping_config()
        mapping = self.get_suppliers_mapping(name=variant_id)

        if not variant_id or not mapping or config.get('supplier') == 'default':
            return self.default_supplier

        try:
            return self.woosupplier_set.get(id=mapping['supplier'])
        except:
            return self.default_supplier

    def get_variant_mapping(self, name=None, default=None, for_extension=False, supplier=None, mapping_supplier=False):
        name = -1 if name == 0 else name
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
        variant_id = -1 if variant_id == 0 else variant_id
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
                    options = v['variant']

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


class WooSupplier(SupplierBase):
    store = models.ForeignKey('WooStore', null=True, related_name='suppliers', on_delete=models.CASCADE)
    product = models.ForeignKey('WooProduct', on_delete=models.CASCADE)

    product_url = models.CharField(max_length=512, null=True, blank=True)
    supplier_name = models.CharField(max_length=512, null=True, blank=True, db_index=True)
    supplier_url = models.CharField(max_length=512, null=True, blank=True)
    shipping_method = models.CharField(max_length=512, null=True, blank=True)
    variants_map = models.TextField(null=True, blank=True)
    is_default = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        if self.supplier_name:
            return self.supplier_name
        elif self.supplier_url:
            return self.supplier_url
        else:
            return '<WooSupplier: {}>'.format(self.id)

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


class WooOrderTrack(OrderTrackBase):
    CUSTOM_TRACKING_KEY = 'woo_custom_tracking'

    store = models.ForeignKey(WooStore, null=True, on_delete=models.CASCADE)
    product_id = models.BigIntegerField()
    woocommerce_status = models.CharField(max_length=128, blank=True, null=True, default='', verbose_name="WooCommerce Fulfillment Status")

    def __str__(self):
        return f'<WooOrderTrack: {self.id}>'


class WooBoard(BoardBase):
    products = models.ManyToManyField('WooProduct', blank=True)

    def __str__(self):
        return f'<WooBoard: {self.id}>'

    def saved_count(self, request=None):
        # Filter non-connected products
        products = self.products.filter(source_id=0)

        if request and request.user.is_subuser:
            # If it's a sub user, only show him products in stores he have access to
            products = products.filter(Q(store__in=request.user.profile.get_woo_stores()) | Q(store=None))

        else:
            # Show the owner product linked to active stores and products with store set to None
            products = products.filter(Q(store__is_active=True) | Q(store=None))

        return products.count()

    def connected_count(self, request=None):
        # Only get products linked to a Shopify product and with an active store
        products = self.products.filter(store__is_active=True).exclude(source_id=0)

        if request and request.user.is_subuser:
            products = products.filter(store__in=request.user.profile.get_woo_stores())

        return products.count()


class WooUserUpload(UserUploadBase):
    product = models.ForeignKey(WooProduct, null=True, on_delete=models.CASCADE)


class WooSyncStatus(OrdersSyncStatusAbstract):
    class Meta:
        verbose_name = 'Woo Sync Status'
        verbose_name_plural = 'Woo Sync Statuses'

    store = models.ForeignKey('woocommerce_core.WooStore',
                              related_name='sync_statuses',
                              on_delete=models.CASCADE)


class WooOrder(WooAPIDataMixin, models.Model):
    class Meta:
        verbose_name = "Woo Order"
        verbose_name_plural = "Woo Orders"

    data = models.TextField()
    store = models.ForeignKey('WooStore', on_delete=models.CASCADE)
    order_id = models.IntegerField(db_index=True)
    date_created = models.DateTimeField(db_index=True)
    status = models.CharField(max_length=20)

    def __str__(self):
        return str(self.order_id)

    def save(self, *args, **kwargs):
        data = self.parsed
        if data.get('id') is not None:
            self.order_id = data['id']
        if data.get('date_created_gmt') is not None:
            self.date_created = arrow.get(data['date_created_gmt']).datetime
        if data.get('status') is not None:
            self.status = data['status']

        super().save(*args, **kwargs)


class WooOrderLine(WooAPIDataMixin, models.Model):
    class Meta:
        verbose_name = "Woo Order Line"
        verbose_name_plural = "Woo Order lines"

    data = models.TextField()
    order = models.ForeignKey('WooOrder', on_delete=models.CASCADE)
    line_id = models.IntegerField(db_index=True)
    product_id = models.IntegerField(db_index=True)

    def __str__(self):
        return str(self.line_id)

    def save(self, *args, **kwargs):
        data = self.parsed
        if data.get('id') is not None:
            self.line_id = data['id']
        if data.get('product_id') is not None:
            self.product_id = data['product_id']

        super().save(*args, **kwargs)


class WooOrderShippingAddress(WooAPIDataMixin, models.Model):
    class Meta:
        verbose_name = "Woo Order Shipping Address"
        verbose_name_plural = "Woo Order Shipping Addresses"

    data = models.TextField()
    order = models.OneToOneField('WooOrder', on_delete=models.CASCADE, related_name='shipping_address')
    first_name = models.CharField(max_length=200)
    last_name = models.CharField(max_length=200)
    company = models.CharField(max_length=200)
    address_1 = models.CharField(max_length=200)
    address_2 = models.CharField(max_length=200)
    city = models.CharField(max_length=200)
    state = models.CharField(max_length=200)
    postcode = models.CharField(max_length=20)
    country = models.CharField(max_length=3)

    def __str__(self):
        return str(self.address_1)

    def save(self, *args, **kwargs):
        data = self.parsed
        if data.get('first_name') is not None:
            self.first_name = data['first_name']
        if data.get('last_name') is not None:
            self.last_name = data['last_name']
        if data.get('company') is not None:
            self.company = data['company']
        if data.get('address_1') is not None:
            self.address_1 = data['address_1']
        if data.get('address_2') is not None:
            self.address_2 = data['address_2']
        if data.get('city') is not None:
            self.city = data['city']
        if data.get('state') is not None:
            self.state = data['state']
        if data.get('postcode') is not None:
            self.postcode = data['postcode']
        if data.get('country') is not None:
            self.country = data['country']

        super().save(*args, **kwargs)


class WooOrderBillingAddress(WooAPIDataMixin, models.Model):
    class Meta:
        verbose_name = "Woo Order Billing Address"
        verbose_name_plural = "Woo Order Billing Addresses"

    data = models.TextField()
    order = models.OneToOneField('WooOrder', on_delete=models.CASCADE, related_name='billing_address')
    first_name = models.CharField(max_length=200)
    last_name = models.CharField(max_length=200)
    company = models.CharField(max_length=200)
    address_1 = models.CharField(max_length=200)
    address_2 = models.CharField(max_length=200)
    city = models.CharField(max_length=200)
    state = models.CharField(max_length=200)
    postcode = models.CharField(max_length=20)
    country = models.CharField(max_length=3)
    email = models.CharField(max_length=100)
    phone = models.CharField(max_length=100)

    def __str__(self):
        return str(self.address_1)

    def save(self, *args, **kwargs):
        data = self.parsed
        if data.get('first_name') is not None:
            self.first_name = data['first_name']
        if data.get('last_name') is not None:
            self.last_name = data['last_name']
        if data.get('company') is not None:
            self.company = data['company']
        if data.get('address_1') is not None:
            self.address_1 = data['address_1']
        if data.get('address_2') is not None:
            self.address_2 = data['address_2']
        if data.get('city') is not None:
            self.city = data['city']
        if data.get('state') is not None:
            self.state = data['state']
        if data.get('postcode') is not None:
            self.postcode = data['postcode']
        if data.get('country') is not None:
            self.country = data['country']
        if data.get('email') is not None:
            self.email = data['email']
        if data.get('phone') is not None:
            self.phone = data['phone']

        super().save(*args, **kwargs)


class WooWebhook(models.Model):
    class Meta:
        verbose_name = "WooCommerce Order Webhooks"
        ordering = ['-created_at']
        unique_together = ('store', 'topic')

    store = models.ForeignKey(WooStore, on_delete=models.CASCADE)
    topic = models.CharField(max_length=60)
    webhook_id = models.BigIntegerField(default=0, verbose_name='Webhook ID')
    call_count = models.IntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'<WooWebhook: {self.id}>'
