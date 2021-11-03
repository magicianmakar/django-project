import arrow
import json
import re
from pusher import Pusher
from urllib.parse import urlparse

from django.conf import settings
from django.db import models
from django.urls import reverse

from shopified_core.models import BoardBase, OrderTrackBase, SupplierBase, UserUploadBase
from shopified_core.utils import get_domain
from suredone_core.models import SureDoneProductBase, SureDoneStoreBase


class EbayStore(SureDoneStoreBase):
    class Meta(SureDoneStoreBase.Meta):
        verbose_name = 'eBay Store'

    def sync(self, instance_title: str, options_data: dict):
        store_index_str = '' if self.store_instance_id == 1 else f'{self.store_instance_id}'
        channel_is_enabled = options_data.get(f'site_ebay{store_index_str}connect') == 'on'
        legacy_auth_token = options_data.get(f'ebay{store_index_str}_token')
        oauth_token = options_data.get(f'ebay{store_index_str}_token_oauth')
        auth_token_exists = bool(legacy_auth_token) or bool(oauth_token)

        self.is_active = channel_is_enabled and auth_token_exists

        # TODO: handle the case when the token is expired
        legacy_token_expires_str = options_data.get(f'ebay{store_index_str}_token_expires')
        oauth_token_expires_str = options_data.get(f'ebay{store_index_str}_token_oauth_expires')

        if legacy_auth_token and legacy_token_expires_str:
            try:
                arrow_date = arrow.get(legacy_token_expires_str, 'YYYY-MM-DD HH:mm:ss')
                self.legacy_auth_token_exp_date = getattr(arrow_date, 'datetime', None)
            except:
                pass

        if oauth_token and oauth_token_expires_str:
            try:
                arrow_date = arrow.get(oauth_token_expires_str, 'YYYY-MM-DD HH:mm:ss')
                self.oauth_token_exp_date = getattr(arrow_date, 'datetime', None)
            except:
                pass

        # Get ebay account title
        self.title = instance_title

        self.save()

    def get_store_url(self):
        return 'https://www.ebay.com'

    def get_admin_url(self, *args):
        return f'{self.get_store_url()}/mys/overview'

    def get_admin_order_details(self, order_id):
        pass

    def get_suppliers(self):
        return []

    def set_default_supplier(self, supplier, commit=False):
        pass

    def connected_count(self):
        pass

    def saved_count(self):
        pass

    def get_short_hash(self):
        return self.store_hash[:8] if self.store_hash else ''

    def pusher_channel(self):
        return f'ebay_{self.get_short_hash()}'

    def pusher_trigger(self, event, data):
        if not settings.PUSHER_APP_ID:
            return

        pusher = Pusher(
            app_id=settings.PUSHER_APP_ID,
            key=settings.PUSHER_KEY,
            secret=settings.PUSHER_SECRET)

        pusher.trigger(self.pusher_channel(), event, data)

    def get_order(self, order_id):
        pass

    def get_product(self, product_id, store):
        pass


class EbayProduct(SureDoneProductBase):
    class Meta(SureDoneProductBase.Meta):
        verbose_name = 'eBay Product'
        ordering = ['-created_at']

    store = models.ForeignKey('EbayStore', related_name='products', null=True, on_delete=models.CASCADE)
    default_supplier = models.ForeignKey('EbaySupplier', on_delete=models.SET_NULL, null=True)

    source_id = models.BigIntegerField(default=0, null=True, blank=True, db_index=True,
                                       verbose_name='eBay Product ID')
    ebay_store_index = models.BigIntegerField(default=1, null=False, blank=False,
                                              verbose_name='eBay Store Instance Index')
    ebay_category_id = models.BigIntegerField(default=0, null=True, blank=True,
                                              verbose_name='eBay Category ID')
    ebay_site_id = models.IntegerField(default=0, null=True, blank=True, verbose_name='eBay Site ID')

    variants_config = models.TextField(null=True)

    _variants_for_details_view = []

    def __str__(self):
        return f'<EbayProduct: {self.id}>'

    @property
    def parsed(self):
        try:
            return json.loads(self.data)
        except:
            return {}

    @property
    def variants_config_parsed(self):
        try:
            return json.loads(self.variants_config)
        except:
            return []

    @property
    def ebay_url(self):
        if self.is_connected:
            return f'https://www.ebay.com/itm/{self.source_id}'
        elif self.some_variants_are_connected:
            connected_variants = self.product_variants.exclude(source_id=0).exclude(source_id=None)
            if connected_variants.count() > 0:
                connected_variant = connected_variants.first()
                return f'https://www.ebay.com/itm/{connected_variant.source_id}'

        return None

    @property
    def variant_edit(self):
        if self.is_connected:
            return reverse('ebay:variants_edit', args=(self.store.id, self.ebay_store_index))

        return None

    @property
    def is_connected(self):
        return bool(self.source_id)

    @property
    def all_children_variants_are_connected(self):
        return self.is_connected and all([i.is_connected for i in self.product_variants.all()])

    @property
    def some_variants_are_connected(self):
        return self.is_connected or any([i.is_connected for i in self.product_variants.all()])

    @property
    def variants_for_details_view(self):
        all_variants_data = self.product_variants.exclude(guid=self.guid)
        try:
            main_variant = self.product_variants.get(guid=self.guid)
            all_variants_data = [main_variant, *all_variants_data]
        except EbayProductVariant.DoesNotExist:
            pass

        return [i.details_for_view for i in all_variants_data]

    def retrieve(self):
        return self

    def retrieve_variants(self):
        return []

    def get_suppliers(self):
        return self.ebaysupplier_set.all().order_by('-is_default')

    def have_supplier(self):
        try:
            return self.default_supplier is not None
        except:
            return False

    def set_default_supplier(self, supplier, commit=False):
        self.default_supplier = supplier

        if commit:
            self.save()

        self.get_suppliers().update(is_default=False)

        supplier.is_default = True
        supplier.save()

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
                domain = domain.replace(f'.{i}', '')

            domain = domain.split('.')[-1]

            return {
                'domain': domain,
                'source': domain.title(),
                'url': url
            }

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

    def get_mapping_config(self):
        try:
            return json.loads(self.mapping_config)
        except:
            return {}

    def get_suppliers_mapping(self, name=None, default=None):
        mapping = {}
        try:
            if self.supplier_map:
                mapping = json.loads(self.supplier_map)
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
            return self.ebaysupplier_set.get(id=mapping['supplier'])
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
            mapping = mapping.get(f'{supplier}_{variant}', default)

        try:
            mapping = json.loads(mapping)
        except:
            pass

        if type(mapping) is int:
            mapping = str(mapping)

        return mapping

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


class EbayProductVariant(models.Model):
    class Meta:
        verbose_name = 'eBay Product Variant'
        ordering = ['created_at']

    parent_product = models.ForeignKey(EbayProduct, to_field='guid', related_name='product_variants',
                                       on_delete=models.CASCADE, verbose_name='Parent Product')
    default_supplier = models.ForeignKey('EbaySupplier', on_delete=models.SET_NULL, null=True,
                                         verbose_name='Variant-specific Supplier')

    # GUID is unique to each product variant
    # i.e. in SureDone each product (including product variants) has a unique GUID
    guid = models.CharField(max_length=100, blank=False, db_index=True, unique=True, verbose_name='SureDone GUID')

    # SKU is unique to each product but is common to the product's variants,
    # i.e. in SureDone each product has a unique SKU, but the product's variants all have the same SKU
    sku = models.CharField(max_length=100, blank=False, db_index=True, verbose_name='SureDone SKU')

    variant_title = models.CharField(max_length=512, blank=True, null=True)
    price = models.FloatField(default=0.0)
    image = models.TextField(blank=True, null=True)
    supplier_sku = models.CharField(max_length=512, blank=True, null=True)
    source_id = models.BigIntegerField(default=0, null=True, blank=True, db_index=True,
                                       verbose_name='eBay Product ID')
    variant_data = models.TextField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    _parsed_variant_data = {}
    _details_for_view = {}

    def __str__(self):
        return f'<EbayProductVariant: id={self.id}, guid={self.guid}>'

    def __setattr__(self, attrname, val):
        super(EbayProductVariant, self).__setattr__(attrname, val)

        if attrname == 'variant_data' and attrname != '_parsed_variant_data':
            self._parsed_variant_data = {}

        # Reset stored details data
        if attrname != '_details_for_view':
            self._details_for_view = {}

    @property
    def is_connected(self):
        return bool(self.source_id)

    @property
    def is_main_variant(self):
        return self.guid == self.sku

    @property
    def details_for_view(self):
        # Map Model's fields to SureDone's field names
        if not self._details_for_view:
            self._details_for_view = {
                'guid': self.guid,
                'sku': self.sku,
                'varianttitle': self.variant_title,
                'price': self.price,
                'image': self.image,
                'suppliersku': self.supplier_sku,
                'is_connected': self.is_connected,
                **self.parsed_variant_data,
            }
        return self._details_for_view

    @property
    def parsed_variant_data(self):
        try:
            if not self._parsed_variant_data:
                self._parsed_variant_data = json.loads(self.variant_data)
        except:
            self._parsed_variant_data = {}

        return self._parsed_variant_data

    def get_suppliers(self):
        return EbaySupplier.objects.filter(product_guid=self.guid).order_by('-is_default')

    @property
    def has_supplier(self):
        try:
            return self.default_supplier is not None or self.parent_product.have_supplier()
        except:
            return False

    @property
    def has_own_supplier(self):
        try:
            return self.default_supplier is not None
        except:
            return False

    @property
    def variant_specific_supplier(self):
        return self.default_supplier if self.default_supplier else self.parent_product.default_supplier

    def set_default_supplier(self, supplier, commit=False):
        self.default_supplier = supplier

        if commit:
            self.save()

        self.get_suppliers().update(is_default=False)

        supplier.is_default = True
        supplier.save()

    def get_original_info(self):
        if self.has_supplier:
            url = self.variant_specific_supplier.product_url

            try:
                domain = urlparse(url).hostname
            except:
                domain = None

            if domain is None:
                return domain

            for i in ['com', 'co.uk', 'org', 'net']:
                domain = domain.replace(f'.{i}', '')

            domain = domain.split('.')[-1]

            return {
                'domain': domain,
                'source': domain.title(),
                'url': url
            }

    def save(self, *args, **kwargs):
        # Reset stored values in case data was updated
        self._parsed_variant_data = {}
        self._details_for_view = {}

        super(EbayProductVariant, self).save(*args, **kwargs)


class EbaySupplier(SupplierBase):
    store = models.ForeignKey('EbayStore', null=True, related_name='suppliers', on_delete=models.CASCADE)
    product_guid = models.CharField(max_length=100, blank=False, db_index=True, default=None, verbose_name='SureDone GUID')
    product = models.ForeignKey(EbayProduct, to_field='guid', on_delete=models.CASCADE)

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
            return f'<EbaySupplier: {self.id}>'

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
                return f'https://www.aliexpress.com/item/{source_id}.html'
            if self.is_ebay:
                return f'https://www.ebay.com/itm/{source_id}'

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

            name = f'Supplier {self.supplier_type()}#{supplier_idx}'

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


ORDER_STATUS_CHOICES = (
    # SureDone's valid values:
    # “INCOMPLETE”, “READY”, “PENDING”, “ORDERED”, “DROPSHIPPED”, “COMPLETE” or “ARCHIVED”
    ('INCOMPLETE', 'INCOMPLETE'),
    ('READY', 'READY'),
    ('PENDING', 'PENDING'),
    ('ORDERED', 'ORDERED'),
    ('DROPSHIPPED', 'DROPSHIPPED'),
    ('COMPLETE', 'COMPLETE'),
    ('ARCHIVED', 'ARCHIVED'),
)


class EbayOrderTrack(OrderTrackBase):
    CUSTOM_TRACKING_KEY = 'ebay_custom_tracking'

    store = models.ForeignKey(EbayStore, null=True, on_delete=models.CASCADE)
    line_id = models.CharField(max_length=512, blank=True, default='', db_index=True,
                               verbose_name="Variant-specific GUID")
    ebay_status = models.CharField(max_length=128, blank=True, null=True, default='',
                                   verbose_name='eBay Fulfillment Status')

    def __str__(self):
        return f'<EbayOrderTrack: {self.id}>'

    def get_ebay_link(self):
        if hasattr(self, 'order') and isinstance(self.order, dict):
            order_id = self.order.get('details', {}).get('ExtendedOrderID')
            if order_id:
                return f'{self.store.get_store_url()}/sh/ord/details?orderid={order_id}'
        return ''


class EbayBoard(BoardBase):
    products = models.ManyToManyField('EbayProduct', blank=True)

    def __str__(self):
        return f'<EbayBoard: {self.id}>'


class EbayUserUpload(UserUploadBase):
    product = models.ForeignKey(EbayProduct, null=True, on_delete=models.CASCADE)
