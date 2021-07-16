from django.urls import path

import acp_core.views

urlpatterns = [
    path('', acp_core.views.ACPIndexView.as_view(), name='acp_index_view'),
    path('search', acp_core.views.ACPUserSearchView.as_view(), name='acp_search_view'),
    path('user/<int:user>', acp_core.views.ACPUserInfoView.as_view(), name='acp_user_view'),
    path('plans', acp_core.views.ACPPlansView.as_view(), name='acp_plans_view'),
    path('plans/add', acp_core.views.ACPAddPlanView.as_view(), name='acp_add_plan_view'),
    path('cards', acp_core.views.ACPCardsView.as_view(), name='acp_cards_view'),
]
