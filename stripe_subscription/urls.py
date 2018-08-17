from django.conf.urls import url

import stripe_subscription.views

urlpatterns = [
    url(r'^customer/source$', stripe_subscription.views.customer_source,
        name='stripe_subscription.views.customer_source'),

    url(r'^customer/source/delete$', stripe_subscription.views.customer_source_delete,
        name='stripe_subscription.views.customer_source_delete'),

    url(r'^trial$', stripe_subscription.views.subscription_trial,
        name='stripe_subscription.views.subscription_trial'),

    url(r'^plan$', stripe_subscription.views.subscription_plan,
        name='stripe_subscription.views.subscription_plan'),

    url(r'^cancel$', stripe_subscription.views.subscription_cancel,
        name='stripe_subscription.views.subscription_cancel'),

    url(r'^invoices/(?P<invoice_id>[\w-]+)/pay$', stripe_subscription.views.invoice_pay,
        name='invoice_pay'),

    url(r'^clippingmagic_subscription$', stripe_subscription.views.clippingmagic_subscription,
        name='stripe_subscription.views.clippingmagic_subscription'),

    url(r'^captchacredit_subscription$', stripe_subscription.views.captchacredit_subscription,
        name='stripe_subscription.views.captchacredit_subscription')
]
