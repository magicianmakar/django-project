from django.conf.urls import patterns, url

import stripe_subscription.views

urlpatterns = patterns(
    '',
    url(r'^customer/source$', stripe_subscription.views.customer_source),
    url(r'^customer/source/delete$', stripe_subscription.views.customer_source_delete),
    url(r'^trial$', stripe_subscription.views.subscription_trial),
    url(r'^plan$', stripe_subscription.views.subscription_plan),
    url(r'^cancel$', stripe_subscription.views.subscription_cancel),
    url(r'^invoices/(?P<invoice_id>[\w-]+)/pay$', stripe_subscription.views.invoice_pay, name='invoice_pay'),
)
