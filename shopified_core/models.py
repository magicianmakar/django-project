from django.db import models

from .utils import ALIEXPRESS_SOURCE_STATUS, safe_str


class StoreBase(models.Model):
    class Meta:
        abstract = True

    list_index = models.IntegerField(default=0)


class SupplierBase(models.Model):
    class Meta:
        abstract = True


class ProductBase(models.Model):
    class Meta:
        abstract = True


class BoardBase(models.Model):
    class Meta:
        abstract = True
        ordering = ['title']


class OrderTrackBase(models.Model):
    class Meta:
        abstract = True
        ordering = ['-created_at']
        index_together = ['store', 'order_id', 'line_id']

    def get_source_status_details(self):
        if self.source_status_details and ',' in self.source_status_details:
            source_status_details = []
            for i in self.source_status_details.split(','):
                source_status_details.append(ALIEXPRESS_SOURCE_STATUS.get(safe_str(i).lower()))

            return ', '.join(set(source_status_details))
        else:
            return ALIEXPRESS_SOURCE_STATUS.get(safe_str(self.source_status_details).lower())

    def get_source_status_color(self):
        if not self.source_status:
            return 'danger'
        elif self.source_status == 'FINISH':
            return 'primary'
        else:
            return 'warning'
