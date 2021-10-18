import json

from django.conf import settings
from django.contrib.auth.models import User
from django.db import models
from django.utils.crypto import get_random_string

from shopified_core.models import ProductBase, StoreBase
from shopified_core.utils import safe_json


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

    def verify_custom_fields_created(self, options):
        all_user_custom_fields = options.get('user_field_names', '').split('*')

        failed_sets = []
        for i, fields_set in enumerate(settings.SUREDONE_CUSTOM_FIELDS_CONFIG):
            failed_fields = [x for x in fields_set.get('name', []) if x not in all_user_custom_fields]
            if len(failed_fields):
                failed_sets.append({**fields_set, 'name': failed_fields})

        return failed_sets

    @property
    def has_business_settings_configured(self):
        options_config = self.parsed_options_config
        return bool(options_config.get('business_country') and options_config.get('business_zip'))


class SureDoneStoreBase(StoreBase):
    class Meta(StoreBase.Meta):
        abstract = True

    sd_account = models.ForeignKey('suredone_core.SureDoneAccount', related_name='stores', on_delete=models.CASCADE,
                                   verbose_name='Parent SureDone Account')
    store_instance_id = models.IntegerField(db_index=True, editable=False, verbose_name='Store\'s instance ID')
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    title = models.CharField(max_length=300, blank=True, default='')

    is_active = models.BooleanField(default=True)
    legacy_auth_token_exp_date = models.DateTimeField(null=True,
                                                      verbose_name='Store legacy authorization token expiration date')
    oauth_token_exp_date = models.DateTimeField(null=True, verbose_name='Store oauth token expiration date')
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


class SureDoneProductBase(ProductBase):
    class Meta(ProductBase.Meta):
        abstract = True
    parsed_media_links = []

    sd_account = models.ForeignKey(SureDoneAccount, related_name='products', null=True, on_delete=models.CASCADE)

    guid = models.CharField(max_length=100, blank=False, db_index=True, unique=True, verbose_name='SureDone GUID')
    sku = models.CharField(max_length=100, blank=False, db_index=True, verbose_name='SureDone SKU')
    product_description = models.TextField(blank=True)
    condition = models.CharField(max_length=255, blank=True, default='New')
    thumbnail_image = models.TextField(blank=True, null=True, verbose_name='Product\'s main thumbnail image')
    media_links_data = models.TextField(blank=True, null=True, verbose_name='Product\'s media links in a JSON string')

    sd_updated_at = models.DateTimeField(null=True, verbose_name='Product last updated in the SureDone DB')

    def __str__(self):
        return f'<SureDoneProduct: {self.id}>'

    @property
    def parsed(self):
        try:
            return json.loads(self.data)
        except:
            return {}

    @property
    def media_links(self):
        try:
            if self.parsed_media_links:
                return self.parsed_media_links
            self.parsed_media_links = json.loads(self.media_links_data)
            return self.parsed_media_links
        except:
            return []

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
        pass

    def retrieve_variants(self):
        pass

    def update_weight_unit(self):
        pass

    def get_images(self):
        return self.media_links

    def get_image(self):
        images = list(self.get_images())
        return images[0] if images else None
