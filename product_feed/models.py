import hashlib
import json

from django.db import models
from django.conf import settings

from leadgalaxy.models import ShopifyStore
from leadgalaxy.utils import aws_s3_get_key

STATUS_CHOICES = (
    (0, 'Pending'),
    (1, 'Generated'),
    (2, 'Generating'),
)


class FeedStatusAbstract(models.Model):
    status = models.IntegerField(default=0, choices=STATUS_CHOICES)

    feed_options = models.TextField(blank=True, null=True)

    revision = models.IntegerField(default=0)
    all_variants = models.BooleanField(default=True)
    include_variants_id = models.BooleanField(default=True)
    default_product_category = models.CharField(max_length=512, blank=True, default='')
    generation_time = models.IntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(null=True, blank=True)
    fb_access_at = models.DateTimeField(null=True, blank=True, verbose_name='Last Facebook Access')
    google_access_at = models.DateTimeField(null=True, blank=True, verbose_name='Last Google Access')

    class Meta:
        abstract = True

    def __str__(self):
        return '{}'.format(self.store.title)

    @property
    def updated_version(self):
        return self.updated_at and self.updated_at.strftime("%s") or '1'

    def get_url(self, revision=None):
        return 'https://{}.s3.amazonaws.com/{}'.format(
            settings.S3_PRODUCT_FEED_BUCKET,
            self.get_filename(revision=revision)
        )

    def feed_exists(self, revision=None):
        return aws_s3_get_key(self.get_filename(revision=revision), settings.S3_PRODUCT_FEED_BUCKET) is not None

    def get_google_settings(self):
        try:
            data = json.loads(self.feed_options)
        except:
            return {}

        return data.get('google_settings') or {}

    def set_google_settings(self, google_settings):
        try:
            data = json.loads(self.feed_options)
        except:
            data = {}

        data['google_settings'] = google_settings

        self.feed_options = json.dumps(data)
        self.save()

    def get_filename(self, revision=None, store_type=''):
        prefix = ''
        if store_type:
            prefix = f'{store_type}/'

        if revision == 3:
            feed_hash = hashlib.md5('u{}{}/{}/{}'.format(prefix, self.store.user.id, self.store.id, revision).encode()).hexdigest()
        else:
            feed_hash = hashlib.md5('u{}{}/{}'.format(prefix, self.store.user.id, self.store.id).encode()).hexdigest()

        return 'feeds/{}.xml'.format(feed_hash)


class FeedStatus(FeedStatusAbstract):
    store = models.OneToOneField(ShopifyStore, on_delete=models.CASCADE)

    class Meta:
        verbose_name = 'Feed Status'
        verbose_name_plural = 'Feed Statuses'


class CommerceHQFeedStatus(FeedStatusAbstract):
    store = models.OneToOneField('commercehq_core.CommerceHQStore', related_name='feedstatus', on_delete=models.CASCADE)

    class Meta:
        verbose_name = 'Commerce HQ Feed Status'
        verbose_name_plural = 'Commerce HQ Feed Statuses'

    def get_filename(self, revision=None, store_type='chq'):
        return super().get_filename(revision=revision, store_type=store_type)


class WooFeedStatus(FeedStatusAbstract):
    store = models.OneToOneField('woocommerce_core.WooStore', related_name='feedstatus', on_delete=models.CASCADE)

    class Meta:
        verbose_name = 'WooCommerce Feed Status'
        verbose_name_plural = 'WooCommerce Feed Statuses'

    def get_filename(self, revision=None, store_type='woo'):
        return super().get_filename(revision=revision, store_type=store_type)


class GearBubbleFeedStatus(FeedStatusAbstract):
    store = models.OneToOneField('gearbubble_core.GearBubbleStore', related_name='feedstatus')

    class Meta:
        verbose_name = 'GearBubble Feed Status'
        verbose_name_plural = 'GearBubble Feed Statuses'

    def get_filename(self, revision=None, store_type='gear'):
        return super().get_filename(revision=revision, store_type=store_type)


class GrooveKartFeedStatus(FeedStatusAbstract):
    store = models.OneToOneField('groovekart_core.GrooveKartStore', related_name='feedstatus')

    class Meta:
        verbose_name = 'GrooveKart Feed Status'
        verbose_name_plural = 'GrooveKart Feed Statuses'

    def get_filename(self, revision=None, store_type='gkart'):
        return super().get_filename(revision=revision, store_type=store_type)


class BigCommerceFeedStatus(FeedStatusAbstract):
    store = models.OneToOneField('bigcommerce_core.BigCommerceStore', related_name='feedstatus', on_delete=models.CASCADE)

    class Meta:
        verbose_name = 'BigCommerce Feed Status'
        verbose_name_plural = 'BigCommerce Feed Statuses'

    def get_filename(self, revision=None, store_type='bigcommerce'):
        return super().get_filename(revision=revision, store_type=store_type)
