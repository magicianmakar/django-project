from django.conf.urls import url

import profit_dashboard.views

urlpatterns = [
    url(r'^$', profit_dashboard.views.index, name='profit_dashboard.views.index'),
    url(r'^facebook/insights$', profit_dashboard.views.facebook_insights, name='profit_dashboard.views.facebook_insights'),
    url(r'^facebook/accounts/remove$', profit_dashboard.views.facebook_remove_account, name='profit_dashboard.views.facebook_remove_account'),
    url(r'^facebook/accounts$', profit_dashboard.views.facebook_accounts, name='profit_dashboard.views.facebook_accounts'),
    url(r'^facebook/campaign$', profit_dashboard.views.facebook_campaign, name='profit_dashboard.views.facebook_campaign'),
    url(r'^other-costs/save$', profit_dashboard.views.save_other_costs, name='profit_dashboard.views.save_other_costs'),
    url(r'^details$', profit_dashboard.views.profit_details, name='profit_dashboard.views.profit_details'),
]
