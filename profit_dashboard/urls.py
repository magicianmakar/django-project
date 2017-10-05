from django.conf.urls import patterns, url

import profit_dashboard.views

urlpatterns = patterns(
    '',
    url(r'^$', profit_dashboard.views.index),
    url(r'^profits$', profit_dashboard.views.profits),
    url(r'^facebook/insights$', profit_dashboard.views.facebook_insights),
    url(r'^facebook/accounts$', profit_dashboard.views.facebook_accounts),
    url(r'^facebook/campaign$', profit_dashboard.views.facebook_campaign),
    url(r'^other-costs/save$', profit_dashboard.views.save_other_costs),
)
