from django.db import models
from django.contrib.auth.models import User

import json

from leadgalaxy.models import ShopifyStore, ShopifyProduct


class DropwowAccount(models.Model):
    user = models.OneToOneField(User, related_name='dropwow_account', on_delete=models.CASCADE)
    email = models.CharField(max_length=2048)
    api_key = models.CharField(max_length=2048)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __unicode__(self):
        return self.email


class DropwowOrderStatus(models.Model):
    store = models.ForeignKey(ShopifyStore, on_delete=models.CASCADE)

    shopify_order_id = models.BigIntegerField()
    shopify_line_id = models.BigIntegerField()

    product = models.ForeignKey(ShopifyProduct, on_delete=models.SET_NULL, null=True, blank=True)
    customer_address = models.TextField(null=True, blank=True)

    order_id = models.CharField(max_length=255, null=True, blank=True, verbose_name='Dropwow Order ID')

    status = models.CharField(max_length=255, null=True, blank=True)

    tracking_number = models.CharField(max_length=255, null=True, blank=True)
    error_message = models.CharField(max_length=255, null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    pending = models.BooleanField(default=False)

    def __unicode__(self):
        return u'<Dropwow Order: {}>'.format(self.order_id)

    def get_address(self):
        try:
            customer_address = json.loads(self.customer_address)
        except:
            customer_address = {}

        return {
            'firstname': customer_address.get('first_name'),
            'lastname': customer_address.get('last_name'),
            's_firstname': customer_address.get('first_name'),
            's_lastname': customer_address.get('last_name'),
            's_country': customer_address.get('country_code'),
            's_city': customer_address.get('city'),
            's_state': customer_address.get('province_code'),
            's_zipcode': customer_address.get('zip'),
            's_address': customer_address.get('address1'),
            's_address_2': customer_address.get('address2'),
        }
