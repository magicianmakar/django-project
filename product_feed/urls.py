from django.conf.urls import url

import product_feed.views

urlpatterns = [
    url(r'^feeds(?:/(?P<store_type>[a-z]+))?$', product_feed.views.product_feeds,
        name='product_feeds'),

    url(r'^feeds(?:/(?P<store_type>[a-z]+))?/(?P<store_id>[0-9a-z]+)(/(?P<revision>[0-9]+))?$',
        product_feed.views.get_product_feed,
        name='get_product_feed'),
]
