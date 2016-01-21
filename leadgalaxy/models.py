from django.db import models

from django.contrib.auth.models import User, Group
from django.template import Context, Template
from django.db.models import Q
from django.utils.functional import cached_property

import re, json, requests

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
        return '%s | %s'%(self.user.username, self.plan.title)

    def get_plan(self):
       try:
          return self.plan
       except:
          return None

    def get_active_stores(self):
        return self.user.shopifystore_set.filter(is_active=True)

    @cached_property
    def get_perms(self):
        return self.plan.permissions.all().values_list('name',flat=True)

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

def user_config(self, name, default_value=None):
    return self.profile.get_config_value(name, default_value)

User.add_to_class("can", user_can)
User.add_to_class("config", user_config)

class ShopifyStore(models.Model):
    class Meta:
        ordering = ['-created_at']

    title = models.CharField(max_length=512, blank=True, default='')
    api_url = models.CharField(max_length=512)
    is_active = models.BooleanField(default=True)

    user = models.ForeignKey(User)

    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Submittion date')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Last update')

    def __unicode__(self):
        return '%s | %s'%(self.title, self.user.username)

    def get_link(self, page, api=False):
        if api:
            url = re.findall('[^/]+@[^@\.]+\.myshopify\.com', self.api_url)[0]
        else:
            url = re.findall('[^@\.]+\.myshopify\.com', self.api_url)[0]

        url = 'https://%s/%s'%(url, page.lstrip('/'))
        return url

    def get_orders_count(self, status='open', fulfillment='unshipped', financial='any', query=''):
        return requests.get(
            url = self.get_link('/admin/orders/count.json', api=True),
            params = {
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

    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Submittion date')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Last update')

    def __unicode__(self):
        return '%s'%(self.token)

class ShopifyProduct(models.Model):
    class Meta:
        ordering = ['-created_at']

    store = models.ForeignKey(ShopifyStore)
    user = models.ForeignKey(User)

    data = models.TextField()
    original_data = models.TextField(default='', blank=True)
    notes = models.TextField(default='', blank=True)
    stat = models.IntegerField(default=0, verbose_name='Publish stat') # 0: not send yet, 1: Sent to Shopify
    shopify_export = models.ForeignKey('ShopifyProductExport', on_delete=models.SET_NULL, null=True, blank=True)
    is_active = models.BooleanField(default=True)

    parent_product = models.ForeignKey('ShopifyProduct', on_delete=models.SET_NULL, null=True, blank=True, verbose_name='Dupliacte of product')

    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Submittion date')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Last update')

    def __unicode__(self):
        try:
            title = json.loads(self.data)['title']
        except:
            title = 'Product'

        return '%s | %s'%(title, self.store.title)

    def shopify_link(self):
        if self.shopify_export and self.shopify_export.shopify_id:
            return self.store.get_link('/admin/products/{}'.format(self.shopify_export.shopify_id))
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
        data = json.loads(self.data)

        url = data.get('original_url')
        source = ''

        if url:
            if 'aliexpress' in url.lower():
                source = 'AliExpress'
            elif 'alibaba' in url.lower():
                source = 'AliBaba'

            return {
                'source': source,
                'url': url
            }

        return None

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
    shopify_id = models.BigIntegerField(default=0, verbose_name='Shopif Product ID')

    store = models.ForeignKey(ShopifyStore)

    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Submittion date')

    def __unicode__(self):
        return '{} | {}'.format(self.shopify_id, self.store.title)

class ShopifyProductImage(models.Model):
    product = models.BigIntegerField(verbose_name="Shopify Product ID")
    variant = models.BigIntegerField(default=0, verbose_name="Shopify Product ID")
    store = models.ForeignKey(ShopifyStore)

    image = models.CharField(max_length=512, blank=True, default='')

    def __unicode__(self):
        return '{} | {}'.format(self.product, self.variant)


class ShopifyBoard(models.Model):
    class Meta:
        ordering = ['title']

    title = models.CharField(max_length=512, blank=True, default='')
    config = models.CharField(max_length=512, blank=True, default='')

    user = models.ForeignKey(User)
    products = models.ManyToManyField(ShopifyProduct, blank=True)

    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Submittion date')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Last update')

class AppPermission(models.Model):
    name = models.CharField(max_length=512, verbose_name="Permission")
    description = models.CharField(max_length=512, blank=True, default='', verbose_name="Permission Description")

    def __unicode__(self):
        return self.description

class GroupPlan(models.Model):
    title = models.CharField(max_length=512, blank=True, default='', verbose_name="Plan Title")
    montly_price = models.FloatField(default=0.0, verbose_name="Price Per Month")
    stores = models.IntegerField(default=0)
    products = models.IntegerField(default=0)
    boards = models.IntegerField(default=0)

    badge_image = models.CharField(max_length=512, blank=True, default='')
    description = models.CharField(max_length=512, blank=True, default='')

    default_plan = models.IntegerField(default=0, choices=YES_NO_CHOICES)

    permissions = models.ManyToManyField(AppPermission, blank=True)

    def __unicode__(self):
        return '%s'%(self.title)

class UserUpload(models.Model):
    class Meta:
        ordering = ['-created_at']

    user = models.ForeignKey(User)
    product = models.ForeignKey(ShopifyProduct, null=True)
    url = models.CharField(max_length=512, blank=True, default='', verbose_name="Upload file URL")

    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Submittion date')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Last update')

    def __unicode__(self):
        return '%s | %s'%(self.url.replace('%2F','/').split('/')[-1], self.user.username)
