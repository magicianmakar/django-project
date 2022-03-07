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


@add_to_class(User, 'get_fb_boards')
def user_get_fb_boards(self):
    if self.is_subuser:
        return self.profile.subuser_parent.get_fb_boards()
    else:
        return self.fbboard_set.all().order_by('title')


class FBStore(SureDoneStoreBase):
    class Meta(SureDoneStoreBase.Meta):
        verbose_name = 'Facebook Store'

    store_name = models.CharField(default='', null=True, blank=True, max_length=100,
                                  verbose_name='Facebook store name')
    commerce_manager_id = models.CharField(default='', null=True, blank=True, max_length=100,
                                           verbose_name='Facebook Commerce Manager ID')

    def sync(self, instance_title: str, options_data: dict):
        store_prefix = f"facebook{'' if self.store_instance_id == 1 else self.store_instance_id}"
        fb_store_data = safe_json(options_data.get(f'plugin_settings_{store_prefix}'))
        fb_sets_data = fb_store_data.get('sets', {})

        self.store_name = fb_sets_data.get('page_shop_name', {}).get('value')
        self.commerce_manager_id = fb_sets_data.get('commerce_manager_id', {}).get('value')

        access_token = fb_store_data.get('creds', {}).get('access_token', {}).get('value')
        self.is_active = bool(access_token)

        # Get facebook account title
        self.title = instance_title

        self.save()

    def get_store_url(self):
        if self.commerce_manager_id:
            return f'https://business.facebook.com/commerce/{self.commerce_manager_id}'
        else:
            return 'https://business.facebook.com/commerce'

    def get_admin_url(self, *args):
        return f"https://business.facebook.com/commerce/{self.commerce_manager_id or ''}"

    def get_short_hash(self):
        return self.store_hash[:8] if self.store_hash else ''

    def pusher_channel(self):
        return f'fb_{self.get_short_hash()}'

    def pusher_trigger(self, event, data):
        if not settings.PUSHER_APP_ID:
            return

        pusher = Pusher(
            app_id=settings.PUSHER_APP_ID,
            key=settings.PUSHER_KEY,
            secret=settings.PUSHER_SECRET)

        pusher.trigger(self.pusher_channel(), event, data)


class FBProduct(SureDoneProductBase):
    class Meta(SureDoneProductBase.Meta):
        verbose_name = 'Facebook Product'
        ordering = ['-created_at']

    store = models.ForeignKey('FBStore', related_name='products', null=True, on_delete=models.CASCADE)
    default_supplier = models.ForeignKey('FBSupplier', on_delete=models.SET_NULL, null=True)

    fb_store_index = models.BigIntegerField(default=1, null=False, blank=False,
                                            verbose_name='Facebook Store Instance Index')
    fb_category_id = models.BigIntegerField(default=0, null=True, blank=True,
                                            verbose_name='Facebook Category ID')
    brand = models.CharField(max_length=255, blank=True, default='', verbose_name='Facebook product brand')
    page_link = models.CharField(max_length=510, blank=True, default='', verbose_name='Product page link')
    status = models.CharField(max_length=50, blank=True, null=True, default='',
                              verbose_name='Product publication status on Facebook')

    def __str__(self):
        return f'<FacebookProduct: {self.id}>'

    @property
    def is_connected(self):
        return self.status == 'active'

    @property
    def is_pending(self):
        return self.status == 'pending'

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
    def fb_url(self):
        """TODO:FB: how do we construct facebook product URL? """
        if self.is_connected:
            return f'https://www.facebook.com/itm/{self.source_id}'
        elif self.some_variants_are_connected:
            connected_variants = self.product_variants.exclude(source_id=0).exclude(source_id=None)
            if connected_variants.count() > 0:
                connected_variant = connected_variants.first()
                return f'https://www.facebook.com/itm/{connected_variant.source_id}'

        return None

    @property
    def boards(self):
        return self.fbboard_set

    @property
    def variant_edit(self):
        return reverse('fb:variants_edit', args=(self.store.id, self.pk))

    @property
    def variants_for_details_view(self):
        all_variants_data = self.product_variants.exclude(guid=self.guid)
        try:
            main_variant = self.product_variants.get(guid=self.guid)
            all_variants_data = [main_variant, *all_variants_data]
        except FBProductVariant.DoesNotExist:
            pass

        return [i.details_for_view for i in all_variants_data]

    def retrieve_variants(self):
        return self.product_variants.all()

    def get_suppliers(self):
        return self.fbsupplier_set.all().order_by('-is_default')

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
            return self.fbsupplier_set.get(id=mapping['supplier'])
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


class FBProductVariant(SureDoneProductVariantBase):
    class Meta:
        verbose_name = 'Facebook Product Variant'
        ordering = ['created_at']

    parent_product = models.ForeignKey(FBProduct, to_field='guid', related_name='product_variants',
                                       on_delete=models.CASCADE, verbose_name='Parent Product')
    default_supplier = models.ForeignKey('FBSupplier', on_delete=models.SET_NULL, null=True,
                                         verbose_name='Variant-specific Supplier')
    status = models.CharField(max_length=50, blank=True, default='',
                              verbose_name='Product publication status on Facebook')

    def __str__(self):
        return f'<FBProductVariant: id={self.id}, guid={self.guid}>'

    @property
    def is_connected(self):
        return self.status == 'active'

    @property
    def is_pending(self):
        return self.status == 'pending'

    def get_suppliers(self):
        return FBSupplier.objects.filter(product_guid=self.guid).order_by('-is_default')

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


class FBSupplier(SureDoneSupplierBase):
    store = models.ForeignKey('FBStore', null=True, related_name='suppliers', on_delete=models.CASCADE)
    product = models.ForeignKey('FBProduct', to_field='guid', on_delete=models.CASCADE)

    def __str__(self):
        if self.supplier_name:
            return self.supplier_name
        elif self.supplier_url:
            return self.supplier_url
        else:
            return f'<FBSupplier: {self.id}>'

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


class FBOrderTrack(OrderTrackBase):
    CUSTOM_TRACKING_KEY = 'fb_custom_tracking'

    store = models.ForeignKey('FBStore', null=True, on_delete=models.CASCADE)
    line_id = models.CharField(max_length=512, blank=True, default='', db_index=True,
                               verbose_name="Variant-specific GUID")
    fb_status = models.CharField(max_length=128, blank=True, null=True, default='',
                                 verbose_name='Facebook Fulfillment Status')

    def __str__(self):
        return f'<FBOrderTrack: {self.id}>'

    def get_fb_link(self):
        if hasattr(self, 'order') and isinstance(self.order, dict):
            order_id = self.order.get('ordernumber')
            if order_id:
                return f'{self.store.get_store_url()}/orders/{order_id}'
        return ''


class FBBoard(BoardBase):
    products = models.ManyToManyField('FBProduct', blank=True)

    def __str__(self):
        return f'<FBBoard: {self.id}>'


class FBUserUpload(UserUploadBase):
    product = models.ForeignKey('FBProduct', null=True, on_delete=models.CASCADE)