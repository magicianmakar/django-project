from django.conf.urls import patterns, url

import product_feed.views

urlpatterns = patterns(
    '',
    url(r'^feeds$', product_feed.views.product_feeds,
        name='product_feeds'),

    url(r'^feeds/(?P<store_id>[0-9a-z]+)(/(?P<revision>[0-9]+))?$',
        product_feed.views.get_product_feed,
        name='get_product_feed'),

)
