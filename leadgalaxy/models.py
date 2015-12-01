from django.db import models

from django.contrib.auth.models import User, Group
from django.template import Context, Template
from django.db.models import Q
import re, json

ENTITY_STATUS_CHOICES = (
    (0, 'Pending'),
    (1, 'Active'),
    (2, 'Inactive'),
    (3, 'Hold'),
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

    def __str__(self):
        return '%s | %s'%(self.user.username, self.plan.title)

    def get_plan(self):
       try:
          return self.plan
       except:
          return None

class ShopifyStore(models.Model):
    class Meta:
        ordering = ['-created_at']

    title = models.CharField(max_length=512, blank=True, default='')
    api_url = models.CharField(max_length=512)

    user = models.ForeignKey(User)

    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Submittion date')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Last update')

    def __unicode__(self):
        return '%s | %s'%(self.title, self.user.username)

class AccessToken(models.Model):
    class Meta:
        ordering = ['-created_at']

    token = models.CharField(max_length=512, unique=True)
    user = models.ForeignKey(User)

    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Submittion date')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Last update')

    def __unicode__(self):
        return '%s | %s'%(self.user.username, self.token)

class ShopifyProduct(models.Model):
    class Meta:
        ordering = ['-created_at']

    store = models.ForeignKey(ShopifyStore)
    user = models.ForeignKey(User)

    data = models.TextField()
    original_data = models.TextField(default='')
    stat = models.IntegerField(default=0, verbose_name='Publish stat') # 0: not send yet, 1: Sent to Shopify
    shopify_id = models.BigIntegerField(default=0, verbose_name='Shopif Product ID')

    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Submittion date')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Last update')

    def __unicode__(self):
        try:
            title = json.loads(self.data)['title']
        except:
            title = 'Product'

        return '%s | %s'%(title, self.store.title)

    def shopify_link(self):
        if self.shopify_id:
            url = re.findall('[^@\.]+\.myshopify\.com', self.store.api_url)[0]
            url = 'https://%s/admin/products/%d'%(url, self.shopify_id)
            return url
        else:
            return None

    def get_product(self):
        try:
            return json.loads(self.data)['title']
        except:
            return None

class ShopifyBoard(models.Model):
    class Meta:
        ordering = ['title']

    title = models.CharField(max_length=512, blank=True, default='')
    config = models.CharField(max_length=512, blank=True, default='')

    user = models.ForeignKey(User)
    products = models.ManyToManyField(ShopifyProduct, blank=True)

    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Submittion date')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Last update')

class GroupPlan(models.Model):
    title = models.CharField(max_length=512, blank=True, default='', verbose_name="Plan Title")
    montly_price = models.FloatField(default=0.0, verbose_name="Price Per Month")
    stores = models.IntegerField(default=0)
    products = models.IntegerField(default=0)
    boards = models.IntegerField(default=0)

    badge_image = models.CharField(max_length=512, blank=True, default='')
    description = models.CharField(max_length=512, blank=True, default='')

    def __unicode__(self):
        return '%s'%(self.title)
