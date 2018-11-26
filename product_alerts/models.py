import simplejson as json
import arrow

from django.db import models
from django.conf import settings
from django.contrib.auth.models import User
from rest_hooks.signals import raw_hook_event

from shopified_core.utils import app_link
from leadgalaxy.models import ShopifyProduct
from commercehq_core.models import CommerceHQProduct
from .utils import parse_sku, variant_index
from leadgalaxy.templatetags.template_helper import price_diff, money_format

PRODUCT_CHANGE_STATUS_CHOICES = (
    (0, 'Pending'),
    (1, 'Applied'),
    (2, 'Failed'),
)


class ProductChange(models.Model):
    class Meta:
        ordering = ['-updated_at']
        index_together = ['user', 'seen', 'hidden']

    user = models.ForeignKey(User, null=True, on_delete=models.CASCADE)
    shopify_product = models.ForeignKey(ShopifyProduct, null=True, on_delete=models.CASCADE)
    chq_product = models.ForeignKey(CommerceHQProduct, null=True, on_delete=models.CASCADE)
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

    @property
    def product_link(self):
        if self.store_type == 'shopify':
            return app_link('product', self.product.id)
        if self.store_type == 'chq':
            return app_link('chq/product', self.product.id)
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
    def get_category_label(cls, category):
        if category == 'product:offline':
            return 'Availability'
        if category == 'variant:quantity':
            return 'Quantity'
        if category == 'variant:price':
            return 'Price'
        if category == 'variant:var_added':
            return 'New Variant'
        if category == 'variant:var_removed':
            return 'Removed Variant'

    def save(self, *args, **kwargs):
        if self.categories != self.get_categories():
            self.categories = self.get_categories()
        super(ProductChange, self).save(*args, **kwargs)

    # send product alert data to subscription hooks
    # sent data should have same structure as response data from fallback api endpoints
    # zapier_core.serializers.ProductAlertSerializer uses this method
    def to_alert(self, category):
        changes = self.get_data(category)
        if not changes:
            return None
        if not category:
            change = changes[0]
            category = '{}:{}'.format(change['level'], change['name'])

        product_title = self.product.title
        original_url = self.product.get_original_info().get('url')
        store = self.product.store
        ret = {
            'category': category,
            'category_label': ProductChange.get_category_label(category),
            'store_type': self.store_type,
            'store_id': store.id,
            'store_title': store.title,
            'product_id': self.product.id,
            'product_title': product_title,
            'product_url_source': original_url,
            'product_url_dropified': self.product_link,
            'description': '',
            'body_text': '',
            'body_html': '',
        }

        headers = []
        data = []
        if category == 'product:offline':
            ret['description'] = 'The Availability of %s has changed.' % product_title
            change = changes[0]
            if not change['new_value']:
                ret['body_text'] = '%s is now Online' % product_title
                ret['body_html'] = '<a href="%s" target="_blank">%s</a> is now <b style="color:green">Online</b>' % (original_url, product_title)
            else:
                ret['body_text'] = '%s is now Offline' % product_title
                ret['body_html'] = '<a href="%s" target="_blank">%s</a> is now <b style="color:red">Offline</b>' % (original_url, product_title)
        if category == 'variant:quantity':
            ret['description'] = 'The Quantity of one or more Variants of %s has changed.' % product_title
            headers = ['Variant', 'Change', 'Old Quantity', 'New Quantity']
            for i, change in enumerate(changes):
                data.append([
                    change['sku_readable'],
                    price_diff(None, change['old_value'], change['new_value'], reverse_colors=False, html=False),
                    change['old_value'],
                    change['new_value']
                ])
        if category == 'variant:price':
            ret['description'] = 'The Price of one or more Variants of %s has changed.' % product_title
            headers = ['Variant', 'Change', 'Old Price', 'New Price']
            for i, change in enumerate(changes):
                data.append([
                    change['sku_readable'],
                    price_diff(None, change['old_value'], change['new_value'], reverse_colors=False, html=False),
                    money_format(change['old_value'], store),
                    money_format(change['new_value'], store)
                ])
        if category == 'variant:var_added':
            ret['description'] = 'A new variant has been added to %s.' % product_title
            headers = ['New Variant']
            for i, change in enumerate(changes):
                data.append([change['sku_readable']])
        if category == 'variant:var_removed':
            ret['description'] = 'A variant has been removed from %s.' % product_title
            headers = ['Removed Variant']
            for i, change in enumerate(changes):
                data.append([change['sku_readable']])
        if len(headers):
            lengths = []
            ret['body_html'] += '<table><thead><tr>'
            for i, header in enumerate(headers):
                lengths.append(len(header))
                ret['body_html'] += '<th>%s</th>' % header
            ret['body_html'] += '</tr></thead><tbody>'
            for i, row in enumerate(data):
                ret['body_html'] += '<tr>'
                for j, value in enumerate(row):
                    if value and len(str(value)) > lengths[j]:
                        lengths[j] = len(str(value))
                    ret['body_html'] += '<td>%s</td>' % value
                ret['body_html'] += '</tr>'
            ret['body_html'] += '</tbody></table>'

            for i, header in enumerate(headers):
                length = str(lengths[i])
                ret['body_text'] += (' {:' + length + 's}  ').format(header)
            ret['body_text'] += "\n"
            for i, header in enumerate(headers):
                length = str(lengths[i])
                ret['body_text'] += ('_{:' + length + 's}_ ').format('_' * lengths[i])
            for i, row in enumerate(data):
                ret['body_text'] += "\n"
                for j, value in enumerate(row):
                    length = str(lengths[j])
                    ret['body_text'] += (' {:' + length + 's}  ').format(str(value))
        return ret

    def send_hook_event_alert(self):
        # Events are filtered in zapier_core.tasks.deliver_hook_wrapper.
        # Query params of hook's target url are used to filter events to be triggered.
        # Following url is hook's target url to get specific event for one shopify product
        # https://hooks.zapier.com/hooks/standard/xxx/xxxxx/?store_type=shopify&store_id=1&product_id=10
        user = self.user
        for category in settings.PRICE_MONITOR_EVENTS.keys():
            payload = self.to_alert(category)
            if payload is not None:
                raw_hook_event.send(
                    sender=None,
                    event_name='alert_created',
                    payload=payload,
                    user=user
                )

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
                ships_from_id = change.get('ships_from_id')
                ships_from_title = change.get('ships_from_title')
                idx = variant_index(self.product, change.get('sku'), variants, ships_from_id, ships_from_title)
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
            ret.pop('level', None)
            return ret

        return None

    def send_hook_event(self, product_data):
        # Events are filtered in zapier_core.tasks.deliver_hook_wrapper.
        # Query params of hook's target url are used to filter events to be triggered.
        # Following url is hook's target url to get specific event for one shopify product
        # https://hooks.zapier.com/hooks/standard/xxx/xxxxx/?store_type=shopify&store_id=1&product_id=10
        user = self.user
        for category in settings.PRICE_MONITOR_EVENTS.keys():
            changes = self.get_data(category)
            for i, change in enumerate(changes):
                payload = self.to_dict(product_data, category, i)
                if payload is not None:
                    raw_hook_event.send(
                        sender=None,
                        event_name=category,
                        payload=payload,
                        user=user
                    )


class ProductVariantPriceHistory(models.Model):
    class Meta:
        ordering = ['-updated_at']
        index_together = [['shopify_product', 'variant_id'], ['chq_product', 'variant_id']]

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    shopify_product = models.ForeignKey(ShopifyProduct, null=True, on_delete=models.CASCADE)
    chq_product = models.ForeignKey(CommerceHQProduct, null=True, on_delete=models.CASCADE)
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
