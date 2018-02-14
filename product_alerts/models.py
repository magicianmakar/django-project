import simplejson as json
import arrow

from django.db import models
from django.contrib.auth.models import User

from leadgalaxy.models import ShopifyProduct
from commercehq_core.models import CommerceHQProduct

PRODUCT_CHANGE_STATUS_CHOICES = (
    (0, 'Pending'),
    (1, 'Applied'),
    (2, 'Failed'),
)


class ProductChange(models.Model):
    class Meta:
        ordering = ['-updated_at']
        index_together = ['user', 'seen', 'hidden']

    user = models.ForeignKey(User, null=True)
    shopify_product = models.ForeignKey(ShopifyProduct, null=True)
    chq_product = models.ForeignKey(CommerceHQProduct, null=True)
    store_type = models.CharField(max_length=255, blank=True, default='shopify')
    data = models.TextField(blank=True, default='')
    hidden = models.BooleanField(default=False, verbose_name='Archived change')
    seen = models.BooleanField(default=False, verbose_name='User viewed the changes')
    status = models.IntegerField(default=0, choices=PRODUCT_CHANGE_STATUS_CHOICES)
    categories = models.CharField(max_length=512, default='', null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    notified_at = models.DateTimeField(null=True, verbose_name='Email Notification Sate')

    def __unicode__(self):
        return u'{}'.format(self.id)

    def orders_count(self, open=True):
        if self.store_type == 'shopify':
            return self.shopify_product.shopifyorderline_set \
                       .exclude(order__fulfillment_status='fulfilled') \
                       .filter(order__closed_at=None, order__cancelled_at=None) \
                       .filter(order__created_at__gte=arrow.now().replace(days=-30).datetime) \
                       .count()
        return 0

    @property
    def product(self):
        if self.store_type == 'shopify':
            return self.shopify_product
        if self.store_type == 'chq':
            return self.chq_product
        return None

    def get_data(self):
        try:
            changes_data = json.loads(self.data)
        except:
            changes_data = []
        return changes_data

    def get_changes_map(self, category):
        changes = self.get_data()

        changes_map = {
            'product': {
                'offline': [],
            },
            'variants': {
                'quantity': [],
                'price': [],
                'var_added': [],
                'var_removed': [],
            }
        }

        if changes and len(changes):
            for change in changes:
                if not category or (change['level'] in category and change['name'] in category):
                    if change.get('level') == 'product':
                        changes_map['product'][change['name']].append(change)
                    if change.get('level') == 'variant':
                        changes_map['variants'][change['name']].append(change)

        return changes_map

    def get_categories(self):
        changes = self.get_data()
        categories = []
        if changes and len(changes):
            for change in changes:
                category = '{}:{}'.format(change['level'], change['name'])
                if category not in categories:
                    categories.append(category)
        return ','.join(categories)

    def save(self, *args, **kwargs):
        if self.categories != self.get_categories():
            self.categories = self.get_categories()
        super(ProductChange, self).save(*args, **kwargs)


class ProductVariantPriceHistory(models.Model):
    class Meta:
        ordering = ['-updated_at']
        index_together = [['shopify_product', 'variant_id'], ['chq_product', 'variant_id']]

    user = models.ForeignKey(User)
    shopify_product = models.ForeignKey(ShopifyProduct, null=True)
    chq_product = models.ForeignKey(CommerceHQProduct, null=True)
    variant_id = models.BigIntegerField(null=True, verbose_name='Source Variant ID')
    data = models.TextField(null=True, blank=True)
    old_price = models.FloatField(null=True)
    new_price = models.FloatField(null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __unicode__(self):
        return u'{}'.format(self.id)

    def add_price(self, new_price, old_price):
        try:
            data = json.loads(self.data)
        except:
            data = []
        self.old_price = old_price
        self.new_price = new_price
        if len(data) == 0:
            data.append(old_price)
        data.append(new_price)
        self.data = json.dumps(data)
        self.save()
