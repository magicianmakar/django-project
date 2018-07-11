import simplejson as json
import arrow

from django.db import models
from django.conf import settings
from django.contrib.auth.models import User
from rest_hooks.signals import raw_hook_event

from leadgalaxy.models import ShopifyProduct
from commercehq_core.models import CommerceHQProduct
from .utils import parse_sku, variant_index

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

    def get_data(self, category=None):
        # returns a list of product changes filtered by category:
        # 'product:offline', 'variant:quantity', 'variant:price', 'variant:var_added', 'variant:var_removed'
        try:
            changes_data = json.loads(self.data)
            changes = []
            for change in changes_data:
                if not category or (change['level'] in category and change['name'] in category):
                    changes.append(change)
        except:
            changes = []
        for idx, change in enumerate(changes):
            sku = change.get('sku')
            if sku:
                options = parse_sku(sku)
                sku = ' / '.join(option.get('option_title', '') for option in options)
                changes[idx]['sku_readable'] = sku

        return changes

    def get_changes_map(self, category=None):
        # returns a map of product changes filtered by category:
        # 'product:offline', 'variant:quantity', 'variant:price', 'variant:var_added', 'variant:var_removed'
        changes = self.get_data(category)

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
                if change.get('level') == 'product':
                    changes_map['product'][change['name']].append(change)
                if change.get('level') == 'variant':
                    changes_map['variants'][change['name']].append(change)

        return changes_map

    def get_categories(self):
        # returns a list of change category names included in data
        changes = self.get_data()
        categories = []
        if changes and len(changes):
            for change in changes:
                category = '{}:{}'.format(change['level'], change['name'])
                if category not in categories:
                    categories.append(category)
        return ','.join(categories)

    @classmethod
    def get_category_from_event(cls, event):
        # returns change category name from hook event name
        # event names are listed in app.settings.PRICE_MONITOR_EVENTS
        if event == 'product_disappeared':
            return 'product:offline'
        if event == 'variant_quantity_changed':
            return 'variant:quantity'
        if event == 'variant_price_changed':
            return 'variant:price'
        if event == 'variant_added':
            return 'variant:var_added'
        if event == 'variant_removed':
            return 'variant:var_removed'

    def save(self, *args, **kwargs):
        if self.categories != self.get_categories():
            self.categories = self.get_categories()
        super(ProductChange, self).save(*args, **kwargs)

    # send product change data to subscription hooks
    # sent data should have same structure as response data from fallback api endpoints
    # zapier_core.serializers.ProductChangeSerializer uses this method
    # zapier_core.views.ZapierSampleList uses this method
    def to_dict(self, product_data, category, change_index):
        ret = {
            'product_id': self.product.id,
            'store_type': self.store_type,
            'store_id': self.product.store_id,
            'product_title': self.product.title,
            'store_title': self.product.store.title,
        }
        changes = self.get_data(category)
        if changes and len(changes):
            change = changes[change_index]
            if product_data is not None and change.get('sku'):
                variants = product_data.get('variants', None)
                idx = variant_index(self.product, change.get('sku'), variants)
                if variants is not None and idx is not None:
                    change['variant_id'] = product_data['variants'][idx]['id']
                    title = product_data['variants'][idx].get('title')
                    if title is None:
                        title = ' / '.join(product_data['variants'][idx].get('variant', []))
                    change['variant_title'] = title
                if variants is None and idx is not None:
                    change['variant_id'] = idx
                    variants_map = self.product.get_variant_mapping(for_extension=True)
                    title = ' / '.join(option['title'] for option in variants_map[idx])
                    change['variant_title'] = title

            ret.update(change)
            return ret

        return None

    def send_hook_event(self, product_data):
        # Events are filtered in zapier_core.tasks.deliver_hook_wrapper.
        # Query params of hook's target url are used to filter events to be triggered.
        # Following url is hook's target url to get specific event for one shopify product
        # https://hooks.zapier.com/hooks/standard/xxx/xxxxx/?store_type=shopify&store_id=1&product_id=10
        user = self.user
        for event in settings.PRICE_MONITOR_EVENTS.keys():
            category = ProductChange.get_category_from_event(event)
            changes = self.get_data(category)
            for i, change in enumerate(changes):
                payload = self.to_dict(product_data, category, i)
                if payload is not None:
                    raw_hook_event.send(
                        sender=None,
                        event_name=event,
                        payload=payload,
                        user=user
                    )


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
