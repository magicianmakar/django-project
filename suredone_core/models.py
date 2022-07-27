import json
import os
import re

from django.conf import settings
from django.contrib.auth.models import User
from django.db import models
from django.utils.crypto import get_random_string

from shopified_core.models import ProductBase, StoreBase, SupplierBase
from shopified_core.utils import get_domain, safe_int, safe_json

sd_default_fields = None


def load_sd_default_fields():
    global sd_default_fields

    if sd_default_fields is None:
        with open(os.path.join(settings.BASE_DIR, 'app/data/sd_default_defined_fields.json')) as f:
            sd_default_fields = json.loads(f.read())

    return sd_default_fields


class InvalidSureDoneStoreInstanceId(Exception):
    def __init__(self, instance_id):
        super(InvalidSureDoneStoreInstanceId, self).__init__(f'Instance ID: {instance_id}')


class SureDoneAccount(StoreBase):
    class Meta(StoreBase.Meta):
        verbose_name = 'SureDone Account'

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    title = models.CharField(max_length=300, blank=True, default='')

    email = models.CharField(max_length=512, verbose_name='SureDone account email')
    password = models.CharField(max_length=100, verbose_name='SureDone account password')
    sd_id = models.CharField(max_length=200, verbose_name='SureDone user ID')

    options_config_data = models.TextField(null=True, blank=True)

    api_username = models.CharField(max_length=512)
    api_token = models.CharField(max_length=512)

    is_active = models.BooleanField(default=True)
    store_hash = models.CharField(default='', max_length=50, editable=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.store_hash:
            self.store_hash = get_random_string(32, 'abcdef0123456789')

        super(SureDoneAccount, self).save(*args, **kwargs)

    def get_store_url(self):
        return 'https://www.suredone.com'

    def get_short_hash(self):
        return self.store_hash[:8] if self.store_hash else ''

    def get_product(self, product_id, store):
        return SureDoneProductBase.objects.get(source_id=product_id, store=store)

    @property
    def parsed_options_config(self):
        return safe_json(self.options_config_data, default={})

    def update_options_config(self, data: dict, overwrite=False, commit=True):
        if overwrite:
            new_config = data
        else:
            new_config = self.parsed_options_config
            new_config.update(data)
        self.options_config_data = json.dumps(new_config)
        if commit:
            self.save()

    def verify_custom_fields_created(self, options: dict):
        all_user_custom_fields = options.get('user_field_names', '').split('*')

        failed_sets = []
        for i, fields_set in enumerate(settings.SUREDONE_CUSTOM_FIELDS_CONFIG):
            missing_field_names = []
            missing_field_labels = []
            all_field_labels = fields_set.get('label', [])
            for field_i, field_name in enumerate(fields_set.get('name', [])):
                if field_name not in all_user_custom_fields:
                    missing_field_names.append(field_name)
                    try:
                        missing_field_labels.append(all_field_labels[field_i])
                    except IndexError:
                        continue

            if len(missing_field_names):
                failed_sets.append({**fields_set, 'name': missing_field_names, 'label': missing_field_labels})

        return failed_sets

    def verify_variation_fields(self, options: dict):
        current_variant_fields = options.get('site_cart_variants', '').split('*')
        return [x for x in settings.SUREDONE_DEFAULT_VARIANTS_FIELDS_CONFIG if x not in current_variant_fields]

    @staticmethod
    def minimize_custom_field_name(field_name: str):
        return ''.join(c for c in field_name if c.isalnum()).lower()

    def format_custom_field(self, field_name):
        minified_key = SureDoneAccount.minimize_custom_field_name(field_name)
        return f'ucf{minified_key}'

    def is_default_field(self, field_name: str) -> bool:
        return field_name.lower() in load_sd_default_fields()

    def has_field_defined(self, field_name: str, options=None):
        if self.is_default_field(field_name):
            return True

        if not options:
            options = self.parsed_options_config
        all_user_custom_fields = options.get('user_field_names', '').split('*')
        return self.format_custom_field(field_name) in all_user_custom_fields

    def has_fields_defined(self, field_names: list, options=None):
        if not options:
            options = self.parsed_options_config
        custom_fields = options.get('user_field_names', '').split('*')

        return all([(self.is_default_field(x) or x in custom_fields or self.format_custom_field(x) in custom_fields)
                    for x in field_names])

    def has_variation_field(self, variation_field: str, options=None):
        if not options:
            options = self.parsed_options_config
        all_var_fields = options.get('site_cart_variants', '').split('*')
        return variation_field.lower() in all_var_fields or self.format_custom_field(variation_field) in all_var_fields

    def has_variation_fields(self, variation_fields: list, options=None):
        if not options:
            options = self.parsed_options_config
        user_var_fields = options.get('site_cart_variants', '').split('*')

        return all([(x.lower() in user_var_fields or self.format_custom_field(x) in user_var_fields)
                   for x in variation_fields])

    @property
    def has_business_settings_configured(self):
        options_config = self.parsed_options_config
        return bool(options_config.get('business_country') and options_config.get('business_zip'))

    def verify_fb_fields_mapping(self, options: dict):
        stores = self.facebook_core_stores.all()
        missing_fields_per_store = {}
        required_field_mappings = {
            'link': 'dropifiedfbproductlink',
            'description': 'longdescription'
        }
        for store in stores:
            prefix = store.instance_prefix
            plugin_settings = safe_json(options.get(f'plugin_settings_{prefix}')).get('sets', {})
            fields_mapping = plugin_settings.get('custom_field_mappings', {}).get('value', {})

            # If there are 0 field mappings, SureDone returns a list for custom_field_mappings.value
            if not isinstance(fields_mapping, dict):
                missing_fields_per_store[store.filter_instance_id] = required_field_mappings

            # If there are some field mappings, verify each mapping pair separately
            else:
                current_missing_pairs = {}
                for key, value in required_field_mappings.items():
                    if fields_mapping.get(key) != value:
                        current_missing_pairs[key] = value

                if current_missing_pairs:
                    # It's important to include the existing field mappings in the request body to update settings
                    # because otherwise they will be erased, i.e. a request to update field mappings overwrites a
                    # list of field mappings that already exists with a new one removing anything that was not included
                    missing_fields_per_store[store.filter_instance_id] = {
                        **fields_mapping,
                        **current_missing_pairs,
                    }

        return missing_fields_per_store

    def verify_google_fields_mapping(self, options: dict):
        stores = self.google_core_stores.all()
        missing_fields_per_store = {}
        required_field_mappings = {
            'link': 'dropifiedgoogleproductlink',
            'description': 'longdescription'
        }
        for store in stores:
            prefix = store.instance_prefix
            plugin_settings = safe_json(options.get(f'plugin_settings_{prefix}')).get('sets', {})
            fields_mapping = plugin_settings.get('custom_field_mappings', {}).get('value', {})

            # If there are 0 field mappings, SureDone returns a list for custom_field_mappings.value
            if not isinstance(fields_mapping, dict):
                missing_fields_per_store[store.filter_instance_id] = required_field_mappings

            # If there are some field mappings, verify each mapping pair separately
            else:
                current_missing_pairs = {}
                for key, value in required_field_mappings.items():
                    if fields_mapping.get(key) != value:
                        current_missing_pairs[key] = value

                if current_missing_pairs:
                    # It's important to include the existing field mappings in the request body to update settings
                    # because otherwise they will be erased, i.e. a request to update field mappings overwrites a
                    # list of field mappings that already exists with a new one removing anything that was not included
                    missing_fields_per_store[store.filter_instance_id] = {
                        **fields_mapping,
                        **current_missing_pairs,
                    }

        return missing_fields_per_store


class SureDoneStoreBase(StoreBase):
    class Meta(StoreBase.Meta):
        abstract = True

    sd_account = models.ForeignKey('suredone_core.SureDoneAccount', related_name='%(app_label)s_stores', on_delete=models.CASCADE,
                                   verbose_name='Parent SureDone Account')
    store_instance_id = models.IntegerField(db_index=True, editable=False, verbose_name='Store\'s instance ID')
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    title = models.CharField(max_length=300, blank=True, default='')

    is_active = models.BooleanField(default=True)
    store_hash = models.CharField(default='', max_length=50, editable=False)

    auto_fulfill = models.CharField(max_length=50, null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.store_hash:
            self.store_hash = get_random_string(32, 'abcdef0123456789')

        try:
            self.auto_fulfill = self.user.get_config('auto_shopify_fulfill', 'enable')
        except User.DoesNotExist:
            pass

        super(SureDoneStoreBase, self).save(*args, **kwargs)

    def get_short_hash(self):
        return self.store_hash[:8] if self.store_hash else ''

    @property
    def filter_instance_id(self):
        # SD assigns store instance IDs in the following order: 0, 2, 3, 4, etc.
        # so if the instance ID is 1, set it to 0
        instance_id = self.store_instance_id
        if not isinstance(instance_id, int):
            instance_id = safe_int(instance_id, None)
            if instance_id is None:
                raise InvalidSureDoneStoreInstanceId(instance_id)

        return 0 if instance_id == 1 else instance_id

    @property
    def instance_prefix_id(self):
        return '' if self.store_instance_id == 1 else f'{self.store_instance_id}'


class SureDoneProductBase(ProductBase):
    class Meta(ProductBase.Meta):
        abstract = True
    parsed_media_links = []

    sd_account = models.ForeignKey(SureDoneAccount, related_name='%(app_label)s_products', null=True, on_delete=models.CASCADE)

    guid = models.CharField(max_length=100, blank=False, db_index=True, unique=True, verbose_name='SureDone GUID')
    sku = models.CharField(max_length=100, blank=False, db_index=True, verbose_name='SureDone SKU')
    source_id = models.BigIntegerField(default=0, null=True, blank=True, db_index=True,
                                       verbose_name='Platform-specific Product ID')
    product_description = models.TextField(blank=True)
    condition = models.CharField(max_length=255, blank=True, default='New')
    thumbnail_image = models.TextField(blank=True, null=True, verbose_name='Product\'s main thumbnail image')
    media_links_data = models.TextField(blank=True, null=True, verbose_name='Product\'s media links in a JSON string')
    variants_config = models.TextField(null=True)
    sd_updated_at = models.DateTimeField(null=True, verbose_name='Product last updated in the SureDone DB')

    _variants_for_details_view = []

    def __str__(self):
        return f'<SureDoneProduct: {self.id}>'

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
    def media_links(self):
        try:
            if self.parsed_media_links:
                return self.parsed_media_links
            self.parsed_media_links = json.loads(self.media_links_data)
            return self.parsed_media_links
        except:
            return []

    @property
    def tags_list(self):
        try:
            return self.tags.split(',')
        except:
            return []

    def get_config(self):
        try:
            return json.loads(self.config)
        except:
            return {}

    @property
    def is_connected(self):
        return bool(self.source_id)

    @property
    def all_children_variants_are_connected(self):
        return self.is_connected and all([i.is_connected for i in self.product_variants.all()])

    @property
    def some_variants_are_connected(self):
        return self.is_connected or any([i.is_connected for i in self.product_variants.all()])

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
        return self

    def retrieve_variants(self):
        return []

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
            mapping = mapping.get(f'{supplier}_{variant}', default)

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

    def update_weight_unit(self):
        pass

    def get_images(self):
        return self.media_links

    def get_image(self):
        images = list(self.get_images())
        return images[0] if images else None


class SureDoneProductVariantBase(models.Model):
    class Meta:
        abstract = True
    parsed_media_links = []

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
                                       verbose_name='Platform-specific Product ID')
    variant_data = models.TextField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    _parsed_variant_data = {}
    _details_for_view = {}

    def __str__(self):
        return f'<SureDoneProductVariant: {self.id}>'

    def __setattr__(self, attrname, val):
        super().__setattr__(attrname, val)

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

    def save(self, *args, **kwargs):
        # Reset stored values in case data was updated
        self._parsed_variant_data = {}
        self._details_for_view = {}

        super().save(*args, **kwargs)


class SureDoneSupplierBase(SupplierBase):
    class Meta(SupplierBase.Meta):
        abstract = True

    product_guid = models.CharField(max_length=100, blank=False, db_index=True, default=None, verbose_name='SureDone GUID')
    product_url = models.CharField(max_length=512, null=True, blank=True)
    supplier_name = models.CharField(max_length=512, null=True, blank=True, db_index=True)
    supplier_url = models.CharField(max_length=512, null=True, blank=True)
    shipping_method = models.CharField(max_length=512, null=True, blank=True)
    variants_map = models.TextField(null=True, blank=True)
    is_default = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'<SureDoneSupplier: {self.id}>'

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
