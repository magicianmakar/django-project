from django.conf.urls import url

import shopify_oauth.views

urlpatterns = [
    url(r'^$', shopify_oauth.views.index, name='shopify_index'),
    url(r'^install/(?P<store>[0-9A-Za-z_-]+)$', shopify_oauth.views.install, name='shopify_install'),
    url(r'^callback$', shopify_oauth.views.callback, name='shopify_callback'),
]
