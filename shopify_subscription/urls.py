from django.conf.urls import url

import shopify_subscription.views

urlpatterns = [
    url(r'^plan$', shopify_subscription.views.subscription_plan, name='shopify_subscription.views.subscription_plan'),
    url(r'^activated$', shopify_subscription.views.subscription_activated, name='shopify_subscription.views.subscription_activated'),
    url(r'^charged/(?P<store>[0-9]+)$', shopify_subscription.views.subscription_charged, name='shopify_subscription.views.subscription_charged'),
    url(r'^subscription-callflex$', shopify_subscription.views.subscription_callflex, name='shopify_subscription.views.subscription_callflex'),
    url(r'^subscription-callflex-activated$', shopify_subscription.views.subscription_callflex_activated,
        name='shopify_subscription.views.subscription_callflex_activated')
]
