from django.conf.urls import patterns, url

import profit_dashboard.views

urlpatterns = patterns(
    '',
    url(r'^$', profit_dashboard.views.index, name='profit_dashboard_index'),
    url(r'^profits$', profit_dashboard.views.profits, name='profit_dashboard_profits'),
    url(r'^facebook/insights$', profit_dashboard.views.facebook_insights, name='profit_dashboard_facebook_insights'),
    url(r'^other-costs/save$', profit_dashboard.views.save_other_costs, name='profit_dashboard_save_other_costs'),
)
