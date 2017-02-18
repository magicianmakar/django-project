from django.conf.urls import patterns, url

import shopified_core.views

urlpatterns = patterns(
    '',
    url(r'^api/(v(?P<version>[0-9])/)?((?P<store_type>[a-z]+)/)?(?P<target>[a-z-]+)$',
        shopified_core.views.ShopifiedApi.as_view(),
        kwargs={'store_type': 'shopify', 'version': 1}),
)
