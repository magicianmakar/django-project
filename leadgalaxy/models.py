from django.db import models

from django.contrib.auth.models import User
from django.template import Context, Template
from django.db.models import Q
import re, json

class ShopifyStore(models.Model):
    title = models.CharField(max_length=512, blank=True, default='')
    api_url = models.CharField(max_length=512)

    user = models.ForeignKey(User)

    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Submittion date')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Last update')

    def __unicode__(self):
        return '%s | %s'%(self.title, self.user.username)

class AccessToken(models.Model):
    token = models.CharField(max_length=512, unique=True)
    user = models.ForeignKey(User)

    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Submittion date')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Last update')

    def __unicode__(self):
        return '%s | %s'%(self.user.username, self.token)

class ShopifyProduct(models.Model):
    store = models.ForeignKey(ShopifyStore)
    user = models.ForeignKey(User)

    data = models.TextField()
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
    title = models.CharField(max_length=512, blank=True, default='')

    user = models.ForeignKey(User)
    products = models.ManyToManyField(ShopifyProduct)

    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Submittion date')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Last update')
