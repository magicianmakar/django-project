from django.conf.urls import patterns, url

import shopify_subscription.views

urlpatterns = patterns(
    '',
    url(r'^plan$', shopify_subscription.views.subscription_plan),
    url(r'^activated$', shopify_subscription.views.subscription_activated),
    url(r'^charged/(?P<store>[0-9]+)$', shopify_subscription.views.subscription_charged),
)
