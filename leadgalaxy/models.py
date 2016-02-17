from django.db import models

from django.contrib.auth.models import User
from django.utils.functional import cached_property

import re
import json
import requests

ENTITY_STATUS_CHOICES = (
    (0, 'Pending'),
    (1, 'Active'),
    (2, 'Inactive'),
    (3, 'Hold'),
)

YES_NO_CHOICES = (
    (0, 'No'),
    (1, 'Yes'),
)


class UserProfile(models.Model):
    user = models.OneToOneField(User, related_name='profile')
    plan = models.ForeignKey('GroupPlan', null=True)

    status = models.IntegerField(default=1, choices=ENTITY_STATUS_CHOICES)

    full_name = models.CharField(max_length=255, blank=True, default='')
    address1 = models.CharField(max_length=255, blank=True, default='')
    city = models.CharField(max_length=255, blank=True, default='')
    state = models.CharField(max_length=255, blank=True, default='')
    country = models.CharField(max_length=255, blank=True, default='')

    config = models.TextField(default='', blank=True)

    def __str__(self):
        return '{} | {}'.format(self.user.username, self.plan.title)

    def get_plan(self):
        try:
            return self.plan
        except:
            return None

    def get_active_stores(self):
        return self.user.shopifystore_set.filter(is_active=True)

    @cached_property
    def get_perms(self):
        return self.plan.permissions.all().values_list('name', flat=True)

    def can(self, perm_name):
        perm_name = perm_name.lower()
        view_perm = perm_name.replace('.use', '.view')
        use_perm = perm_name.replace('.view', '.use')
        for i in self.get_perms:
            i = i.lower()
            if perm_name.endswith('.view'):
                if i == view_perm or i == use_perm:
                    return True
            else:
                if i == perm_name:
                    return True

        return False

    def get_config(self):
        try:
            return json.loads(self.config)
        except:
            return {}

    def get_config_value(self, name, default=None):
        return self.get_config().get(name, default)

    def set_config_value(self, name, value):
        data = self.get_config()
        data[name] = value

        self.config = json.dumps(data)
        self.save()


def user_can(self, perms):
    return self.profile.can(perms)


def user_get_config(self, name, default_value=None):
    return self.profile.get_config_value(name, default_value)


def user_set_config(self, name, value):
    return self.profile.set_config_value(name, value)

User.add_to_class("can", user_can)
User.add_to_class("get_config", user_get_config)
User.add_to_class("set_config", user_set_config)


class ShopifyStore(models.Model):
    class Meta:
        ordering = ['-created_at']

    title = models.CharField(max_length=512, blank=True, default='')
    api_url = models.CharField(max_length=512)
    is_active = models.BooleanField(default=True)

    user = models.ForeignKey(User)

    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Submission date')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Last update')

    def __str__(self):
        return self.title

    def get_link(self, page=None, api=False):
        if api:
            url = re.findall('[^/]+@[^@\.]+\.myshopify\.com', self.api_url)[0]
        else:
            url = re.findall('[^@\.]+\.myshopify\.com', self.api_url)[0]

        if page:
            url = 'https://{}/{}'.format(url, page.lstrip('/'))
        else:
            url = 'https://{}'.format(url)

        return url

    def get_orders_count(self, status='open', fulfillment='unshipped', financial='any', query=''):
        return requests.get(
            url=self.get_link('/admin/orders/count.json', api=True),
            params={
                'status': status,
                'fulfillment_status': fulfillment,
                'financial_status': financial,
                'query': query
            }
        ).json()['count']


class AccessToken(models.Model):
    class Meta:
        ordering = ['-created_at']

    token = models.CharField(max_length=512, unique=True)
    user = models.ForeignKey(User)

    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Submission date')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Last update')

    def __unicode__(self):
        return self.token


class ShopifyProduct(models.Model):
    class Meta:
        ordering = ['-created_at']

    store = models.ForeignKey(ShopifyStore)
    user = models.ForeignKey(User)

    data = models.TextField()
    original_data = models.TextField(default='', blank=True)
    variants_map = models.TextField(default='', blank=True)
    notes = models.TextField(default='', blank=True)
    stat = models.IntegerField(default=0, verbose_name='Publish stat')  # 0: not send yet, 1: Sent to Shopify
    shopify_export = models.ForeignKey('ShopifyProductExport', on_delete=models.SET_NULL, null=True, blank=True)
    is_active = models.BooleanField(default=True)

    parent_product = models.ForeignKey('ShopifyProduct', on_delete=models.SET_NULL, null=True, blank=True, verbose_name='Dupliacte of product')

    price_notification_id = models.IntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Submission date')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Last update')

    def __str__(self):
        try:
            title = json.loads(self.data)['title']
        except:
            title = 'Product'

        return title

    def shopify_link(self):
        if self.shopify_export and self.shopify_export.shopify_id:
            return self.store.get_link('/admin/products/{}'.format(self.shopify_export.shopify_id))
        else:
            return None

    def get_shopify_id(self):
        if self.shopify_export and self.shopify_export.shopify_id:
            return self.shopify_export.shopify_id
        else:
            return None

    def get_product(self):
        try:
            return json.loads(self.data)['title']
        except:
            return None

    def get_images(self):
        return json.loads(self.data)['images']

    def get_original_info(self):
        from urlparse import urlparse

        data = json.loads(self.data)

        url = data.get('original_url')
        if url:
            parsed_uri = urlparse(url)
            domain = parsed_uri.netloc.split('.')[-2]

            return {
                'source': domain.title(),
                'url': url
            }

        return None

    def get_supplier_info(self):
        data = json.loads(self.data)
        return data.get('store')

    def set_original_url(self, url):
        data = json.loads(self.data)
        if url != data.get('original_url'):
            data['original_url'] = url
            self.data = json.dumps(data)
            self.save()

            return True

        return False

    def set_shopify_id_from_url(self, url):
        if url and url.strip():
            try:
                pid = re.findall('/([0-9]+)$', url)[0]
            except:
                return False
        else:
            pid = 0

        if self.shopify_export:
            self.shopify_export.shopify_id = pid
            self.shopify_export.save()

        return pid


class ShopifyProductExport(models.Model):
    class Meta:
        ordering = ['-created_at']

    original_url = models.CharField(max_length=512, blank=True, default='')
    shopify_id = models.BigIntegerField(default=0, verbose_name='Shopify Product ID')

    store = models.ForeignKey(ShopifyStore)

    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Submission date')

    def __str__(self):
        return '{}'.format(self.shopify_id)


class ShopifyProductImage(models.Model):
    product = models.BigIntegerField(verbose_name="Shopify Product ID")
    variant = models.BigIntegerField(default=0, verbose_name="Shopify Product ID")
    store = models.ForeignKey(ShopifyStore)

    image = models.CharField(max_length=512, blank=True, default='')

    def __unicode__(self):
        return '{} | {}'.format(self.product, self.variant)


class ShopifyOrder(models.Model):
    class Meta:
        ordering = ['-created_at']

    user = models.ForeignKey(User)
    store = models.ForeignKey(ShopifyStore, null=True)
    order_id = models.BigIntegerField()
    line_id = models.BigIntegerField()
    source_id = models.BigIntegerField(default=0, verbose_name="Source Order ID")
    source_status = models.CharField(max_length=128, blank=True, default='', verbose_name="Source Order Status")
    source_tracking = models.CharField(max_length=128, blank=True, default='', verbose_name="Source Tracking Number")
    hidden = models.BooleanField(default=False)
    check_count = models.IntegerField(default=0)
    data = models.TextField(blank=True, default='')

    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Submission date')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Last update')
    status_updated_at = models.DateTimeField(auto_now_add=True, verbose_name='Last Status Update')

    def encoded(self):
        return json.dumps(self.data).encode('base64')

    def get_shopify_link(self):
        return self.store.get_link('/admin/orders/{}'.format(self.order_id))

    def get_source_status(self):
        status_map = {
            "PLACE_ORDER_SUCCESS": "Awaiting Payment",
            "IN_CANCEL": "Awaiting Cancellation",
            "WAIT_SELLER_SEND_GOODS": "Awaiting Shipment",
            "SELLER_PART_SEND_GOODS": "Partial Shipment",
            "WAIT_BUYER_ACCEPT_GOODS": "Awaiting delivery",
            "WAIT_GROUP_SUCCESS": "Pending operation success",
            "FINISH": "Order Completed",
            "IN_ISSUE": "Dispute Orders",
            "IN_FROZEN": "Frozen Orders",
            "WAIT_SELLER_EXAMINE_MONEY": "Payment not yet confirmed",
            "RISK_CONTROL": "Payment being verified",
            "IN_PRESELL_PROMOTION": "Promotion is on",
        }

        return status_map.get(self.source_status)

    get_source_status.admin_order_field = 'source_status'

    def get_source_status_color(self):
        if not self.source_status:
            return 'danger'
        elif self.source_status == 'FINISH':
            return 'primary'
        else:
            return 'warning'

    def get_source_url(self):
        if self.source_id:
            return 'http://trade.aliexpress.com/order_detail.htm?orderId={}'.format(self.source_id)
        else:
            return None

    def __str__(self):
        return '{} | {}'.format(self.order_id, self.line_id)


class ShopifyBoard(models.Model):
    class Meta:
        ordering = ['title']

    title = models.CharField(max_length=512, blank=True, default='')
    config = models.CharField(max_length=512, blank=True, default='')

    user = models.ForeignKey(User)
    products = models.ManyToManyField(ShopifyProduct, blank=True)

    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Submission date')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Last update')


class ShopifyWebhook(models.Model):
    class Meta:
        ordering = ['-created_at']

    store = models.ForeignKey(ShopifyStore)
    topic = models.CharField(max_length=64)
    token = models.CharField(max_length=64)
    shopify_id = models.BigIntegerField(default=0, verbose_name='Webhook Shopify ID')
    call_count = models.IntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.token

    def detach(self):
        """ Remove the webhook from Shopify """

        if not self.shopify_id:
            return

        import requests
        endpoint = self.store.get_link('/admin/webhooks/{}.json'.format(self.shopify_id), api=True)
        try:
            requests.delete(endpoint)
        except Exception as e:
            print 'WEBHOOK: detach excption', repr(e)
            return None


class AppPermission(models.Model):
    name = models.CharField(max_length=512, verbose_name="Permission")
    description = models.CharField(max_length=512, blank=True, default='', verbose_name="Permission Description")

    def __str__(self):
        return self.description


class GroupPlan(models.Model):
    title = models.CharField(max_length=512, blank=True, default='', verbose_name="Plan Title")
    montly_price = models.FloatField(default=0.0, verbose_name="Price Per Month")
    stores = models.IntegerField(default=0)
    products = models.IntegerField(default=0)
    boards = models.IntegerField(default=0)
    register_hash = models.CharField(blank=True, default='', max_length=50)

    badge_image = models.CharField(max_length=512, blank=True, default='')
    description = models.CharField(max_length=512, blank=True, default='')

    default_plan = models.IntegerField(default=0, choices=YES_NO_CHOICES)

    permissions = models.ManyToManyField(AppPermission, blank=True)

    def __str__(self):
        return self.title


class UserUpload(models.Model):
    class Meta:
        ordering = ['-created_at']

    user = models.ForeignKey(User)
    product = models.ForeignKey(ShopifyProduct, null=True)
    url = models.CharField(max_length=512, blank=True, default='', verbose_name="Upload file URL")

    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Submission date')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Last update')

    def __str__(self):
        return self.url.replace('%2F', '/').split('/')[-1]


class PlanRegistration(models.Model):
    class Meta:
        ordering = ['-created_at']

    plan = models.ForeignKey(GroupPlan)
    user = models.ForeignKey(User, null=True)
    register_hash = models.CharField(max_length=40, unique=True)
    data = models.CharField(max_length=512, blank=True, default='')
    expired = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Submission date')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Last update')

    def __str__(self):
        return '{} | {}'.format(self.plan.title, self.register_hash)
