from django.db import models

from leadgalaxy.models import ShopifyStore

STATUS_CHOICES = (
    (0, 'Pending'),
    (1, 'Generated'),
    (2, 'Generating'),
)


class FeedStatus(models.Model):
    store = models.OneToOneField(ShopifyStore)
    status = models.IntegerField(default=0, choices=STATUS_CHOICES)

    revision = models.IntegerField(default=0)
    all_variants = models.BooleanField(default=True)
    generation_time = models.IntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(null=True, blank=True)
    fb_access_at = models.DateTimeField(null=True, blank=True, verbose_name='Last Facebook Access')

    def __unicode__(self):
        return '{}'.format(self.store.title)
