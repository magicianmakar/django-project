from django.conf.urls import patterns, url

import dropwow_core.views

urlpatterns = patterns(
    '',
    url(r'^$', dropwow_core.views.marketplace, name="index"),
    url(r'^categories/$', dropwow_core.views.marketplace_categories, name="categories"),
    url(r'^product/(?P<dropwow_product_id>[0-9]+)$', dropwow_core.views.dropwow_product, name="product"),
)
