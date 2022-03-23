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

    url(r'^apply_cancellation_coupon$', stripe_subscription.views.subscription_apply_cancellation_coupon,
        name='stripe_subscription.views.subscription_apply_cancellation_coupon'),

    url(r'^activate$', stripe_subscription.views.subscription_activate,
        name='stripe_subscription.views.subscription_activate'),

    url(r'^custom-cancel$', stripe_subscription.views.custom_subscription_cancel,
        name='stripe_subscription.views.custom_subscription_cancel'),

    url(r'^invoices/(?P<invoice_id>[\w-]+)/pay$', stripe_subscription.views.invoice_pay,
        name='invoice_pay'),

    url(r'^clippingmagic_subscription$', stripe_subscription.views.clippingmagic_subscription,
        name='stripe_subscription.views.clippingmagic_subscription'),

    url(r'^captchacredit_subscription$', stripe_subscription.views.captchacredit_subscription,
        name='stripe_subscription.views.captchacredit_subscription'),

    url(r'^callflexcredit_subscription$', stripe_subscription.views.callflexcredit_subscription,
        name='stripe_subscription.views.callflexcredit_subscription'),

    url(r'^callflex_subscription$', stripe_subscription.views.callflex_subscription,
        name='stripe_subscription.views.callflex_subscription')
]
