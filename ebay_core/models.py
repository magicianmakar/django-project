import arrow
import json
from pusher import Pusher
from urllib.parse import urlparse

from django.conf import settings
from django.contrib.auth.models import User
from django.db import models
from django.urls import reverse

from shopified_core.decorators import add_to_class
from shopified_core.models import BoardBase, OrderTrackBase, UserUploadBase
from shopified_core.utils import safe_json
from suredone_core.models import SureDoneProductBase, SureDoneProductVariantBase, SureDoneStoreBase, SureDoneSupplierBase
from suredone_core.utils import SureDoneUtils, sd_customer_address


@add_to_class(User, 'get_ebay_boards')
def user_get_ebay_boards(self):
    if self.is_subuser:
        return self.profile.subuser_parent.get_ebay_boards()
    else:
        return self.ebayboard_set.all().order_by('title')


class EbayStore(SureDoneStoreBase):
    class Meta(SureDoneStoreBase.Meta):
        verbose_name = 'eBay Store'

    store_username = models.CharField(default='', null=True, blank=True, max_length=100,
                                      verbose_name='eBay store username')
    legacy_auth_token_exp_date = models.DateTimeField(null=True,
                                                      verbose_name='Store legacy authorization token expiration date')
    oauth_token_exp_date = models.DateTimeField(null=True, verbose_name='Store oauth token expiration date')

    @property
    def instance_prefix(self):
        return f'ebay{self.instance_prefix_id}'

    def sync(self, instance_title: str, options_data: dict):
        store_index_str = '' if self.store_instance_id == 1 else f'{self.store_instance_id}'
        self.store_username = safe_json(options_data.get(f'ebay{store_index_str}_user_data')).get('UserID')
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

        # Handle the case when the channel is disabled by errors
        store_is_disabled_by_errors = options_data.get(
            f'ebay{store_index_str}_description_about') == 'Channel has been disabled by errors'
        if not channel_is_enabled and store_is_disabled_by_errors:
            self.is_active = True
            self.title = f'{instance_title} (Store has been disabled)'

        self.save()

    def get_store_url(self):
        if self.store_username:
            return f'https://www.ebay.com/usr/{self.store_username}'
        else:
            return 'https://www.ebay.com'

    def get_admin_url(self, *args):
        return 'https://www.ebay.com/mys/overview'

    def get_admin_order_details(self, order_id):
        return f'{self.get_store_url()}/sh/ord/details?orderid={order_id}'

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

    def get_product(self, product_id, store):
        pass

    def get_order(self, order_id):
        r = SureDoneUtils(user=self.user.models_user).api.get_order_details(order_id)
        orders_data = r.get('orders', [])

        if isinstance(orders_data, list) and len(orders_data) > 0:
            order_data = orders_data[0]
            order_data['order_number'] = order_data.get('oid')
            order_data['created_at'] = order_data.get('date')
            get_config = self.user.models_user.get_config
            order_data['shipping_address'] = sd_customer_address(
                order_data.get('shipping'),
                order_data.get('billing').get('phone'),
                german_umlauts=get_config('_use_german_umlauts', False),
                shipstation_fix=True,
            )
            order_data['line_items'] = order_data.pop('items')
            return order_data

        return None


class EbayProduct(SureDoneProductBase):
    class Meta(SureDoneProductBase.Meta):
        verbose_name = 'eBay Product'
        ordering = ['-created_at']

    store = models.ForeignKey('EbayStore', related_name='products', null=True, on_delete=models.CASCADE)
    default_supplier = models.ForeignKey('EbaySupplier', on_delete=models.SET_NULL, null=True)

    ebay_store_index = models.BigIntegerField(default=1, null=False, blank=False,
                                              verbose_name='eBay Store Instance Index')
    ebay_category_id = models.BigIntegerField(default=0, null=True, blank=True,
                                              verbose_name='eBay Category ID')
    ebay_site_id = models.IntegerField(default=0, null=True, blank=True, verbose_name='eBay Site ID')

    def __str__(self):
        return f'<EbayProduct: {self.id}>'

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
    def boards(self):
        return self.ebayboard_set

    @property
    def variant_edit(self):
        return reverse('ebay:variants_edit', args=(self.store.id, self.pk))

    @property
    def variants_for_details_view(self):
        all_variants_data = self.product_variants.exclude(guid=self.guid)
        try:
            main_variant = self.product_variants.get(guid=self.guid)
            all_variants_data = [main_variant, *all_variants_data]
        except EbayProductVariant.DoesNotExist:
            pass

        return [i.details_for_view for i in all_variants_data]

    def retrieve_variants(self):
        return self.product_variants.all()

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
            source = {
                'aliexpress': 'AliExpress',
                'ebay': 'eBay',
            }.get(domain.lower(), domain.title())

            return {
                'domain': domain,
                'source': source,
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

    def save(self, *args, smart_board_sync=True, **kwargs):
        # Perform smart board sync
        if smart_board_sync:
            from .tasks import do_smart_board_sync_for_product
            do_smart_board_sync_for_product.apply_async(kwargs={
                'user_id': self.user.id,
                'product_id': self.id
            }, countdown=5)

        super().save(*args, **kwargs)

    def get_all_variants_mapping(self):
        all_mapping = {}

        for supplier in self.get_suppliers():
            variants_map = self.get_variant_mapping(supplier=supplier)

            seen_variants = []
            for variant in self.retrieve_variants():
                mapped = variants_map.get(variant.guid)
                if mapped:
                    options = mapped
                else:
                    var_attributes_keys = [i.get('title').replace(' ', '') for i in self.variants_config_parsed]
                    options = []
                    if len(var_attributes_keys):
                        var_data = variant.parsed_variant_data
                        options = [{'title': var_data.get(key), 'image': False} for key in var_attributes_keys]
                        options[0]['image'] = variant.image

                try:
                    if type(options) not in [list, dict]:
                        options = json.loads(options)

                        if type(options) is int:
                            options = str(options)
                except:
                    pass

                variants_map[str(variant.guid)] = options
                seen_variants.append(str(variant.guid))

            for k in list(variants_map.keys()):
                if k not in seen_variants:
                    del variants_map[k]

            all_mapping[str(supplier.id)] = variants_map

        return all_mapping


class EbayProductVariant(SureDoneProductVariantBase):
    class Meta(SureDoneProductVariantBase.Meta):
        verbose_name = 'eBay Product Variant'
        ordering = ['created_at']

    parent_product = models.ForeignKey(EbayProduct, to_field='guid', related_name='product_variants',
                                       on_delete=models.CASCADE, verbose_name='Parent Product')
    default_supplier = models.ForeignKey('EbaySupplier', on_delete=models.SET_NULL, null=True,
                                         verbose_name='Variant-specific Supplier')

    def __str__(self):
        return f'<EbayProductVariant: id={self.id}, guid={self.guid}>'

    @property
    def details_for_view(self):
        return {
            **super(EbayProductVariant, self).details_for_view,
            **self.map_variant_fields_to_ebay_specifics(),
        }

    def map_variant_fields_to_ebay_specifics(self):
        variants_config = self.parent_product.variants_config_parsed
        variant_field_keys = [i.get('title') for i in variants_config if i.get('title')]
        mapped_data = {}
        for key in variant_field_keys:
            mapped_data[f'ebayitemspecifics{key}'] = self.parsed_variant_data[key.replace(' ', '').lower()]
        return mapped_data

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
            source = {
                'aliexpress': 'AliExpress',
                'ebay': 'eBay',
            }.get(domain.lower(), domain.title())

            if source == 'aliexpress':
                source = 'AliExpress'
            elif source == 'ebay':
                source = 'eBay'
            else:
                source = source.title()

            return {
                'domain': domain,
                'source': source,
                'url': url
            }


class EbaySupplier(SureDoneSupplierBase):
    store = models.ForeignKey('EbayStore', null=True, related_name='suppliers', on_delete=models.CASCADE)
    product = models.ForeignKey(EbayProduct, to_field='guid', on_delete=models.CASCADE)

    def __str__(self):
        if self.supplier_name:
            return self.supplier_name
        elif self.supplier_url:
            return self.supplier_url
        else:
            return f'<EbaySupplier: {self.id}>'

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
