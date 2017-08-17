from django.conf.urls import patterns, url

import plan_checkout.views

urlpatterns = patterns(
    '',
    url(r'^checkout$', plan_checkout.views.PlanCheckoutView.as_view()),
    url(r'^ty$', plan_checkout.views.PurchaseThankYouView.as_view()),
    url(r'^(?P<ecom_jam>(jam))?/?(?P<plan_price>(47|99))$', plan_checkout.views.MonthlyCheckoutView.as_view()),
    url(r'^(?P<ecom_jam>(jam))?/?(?P<plan_price>(47|99))/ty$', plan_checkout.views.PurchaseThankYouView.as_view()),
)
