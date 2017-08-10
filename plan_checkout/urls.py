from django.conf.urls import patterns, url

import plan_checkout.views

urlpatterns = patterns(
    '',
    url(r'^checkout$', plan_checkout.views.PlanCheckoutView.as_view()),
    url(r'^ty$', plan_checkout.views.LifetimePurchaseThankYouView.as_view()),
)
