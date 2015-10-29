from django.db import models

from django.contrib.auth.models import User
from django.template import Context, Template
from django.db.models import Q

class ShopifyStore(models.Model):
    title = models.CharField(max_length=512, blank=True, default='')
    api_url = models.CharField(max_length=512)

    user = models.ForeignKey(User)

    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Submittion date')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Last update')

    def __unicode__(self):
        return self.title

class AccessToken(models.Model):
    token = models.CharField(max_length=512, unique=True)
    user = models.ForeignKey(User)

    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Submittion date')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Last update')

    def __unicode__(self):
        return self.token

class ShopifyProduct(models.Model):
    store = models.ForeignKey(ShopifyStore)
    user = models.ForeignKey(User)

    data = models.TextField()
    stat = models.IntegerField(default=0, verbose_name='Publish stat')

    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Submittion date')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Last update')

    def __unicode__(self):
        return self.token
