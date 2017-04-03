from django.db import models

from leadgalaxy.models import ShopifyStore

STATUS_CHOICES = (
    (0, 'Pending'),
    (1, 'Generated'),
    (2, 'Generating'),
)


class FeedStatusAbstract(models.Model):
    status = models.IntegerField(default=0, choices=STATUS_CHOICES)

    revision = models.IntegerField(default=0)
    all_variants = models.BooleanField(default=True)
    include_variants_id = models.BooleanField(default=True)
    generation_time = models.IntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(null=True, blank=True)
    fb_access_at = models.DateTimeField(null=True, blank=True, verbose_name='Last Facebook Access')

    class Meta:
        abstract = True

    def __unicode__(self):
        return '{}'.format(self.store.title)

    def get_url(self):
        from django.conf import settings

        return 'https://{}.s3.amazonaws.com/{}'.format(
            settings.S3_PRODUCT_FEED_BUCKET,
            self.get_filename()
        )

    def feed_exists(self):
        from django.conf import settings
        from leadgalaxy.utils import aws_s3_get_key

        return aws_s3_get_key(self.get_filename(), settings.S3_PRODUCT_FEED_BUCKET) is not None


class FeedStatus(FeedStatusAbstract):
    store = models.OneToOneField(ShopifyStore)

    class Meta:
        verbose_name = 'Feed Status'
        verbose_name_plural = 'Feed Statuses'

    def get_filename(self):
        import hashlib

        feed_hash = hashlib.md5('u{}/{}'.format(self.store.user.id, self.store.id)).hexdigest()
        return 'feeds/{}.xml'.format(feed_hash)


class CommerceHQFeedStatus(FeedStatusAbstract):
    store = models.OneToOneField('commercehq_core.CommerceHQStore', related_name='feedstatus')

    class Meta:
        verbose_name = 'Commerce HQ Feed Status'
        verbose_name_plural = 'Commerce HQ Feed Statuses'

    def get_filename(self):
        import hashlib

        feed_hash = hashlib.md5('u{}/{}/{}'.format('chq', self.store.user.id, self.store.id)).hexdigest()
        return 'feeds/{}.xml'.format(feed_hash)
