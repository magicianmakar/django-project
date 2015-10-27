from django.conf.urls import patterns, include, url

import repport.views

urlpatterns = patterns('',
    url(r'^$', repport.views.index, name='index'),
    url(r'^logout$', repport.views.logout),

    url(r'^api/(?P<target>[a-z-]+)$', repport.views.api),

    url(r'^shopify-api$', repport.views.shopify),

    url(r'^accounts/register$', repport.views.register, name='register'),
)
