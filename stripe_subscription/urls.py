from django.conf.urls import patterns, url

import stripe_subscription.views

urlpatterns = patterns(
    '',
    url(r'^customer/source$', stripe_subscription.views.customer_source),
    url(r'^trial$', stripe_subscription.views.subscription_trial),
    url(r'^plan$', stripe_subscription.views.subscription_plan),
)
