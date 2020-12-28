from django.urls import path

import acp_core.views

urlpatterns = [
    path('', acp_core.views.ACPIndexView.as_view(), name='acp_index_view'),
    path('search', acp_core.views.ACPUserSearchView.as_view(), name='acp_search_view'),
    path('plans', acp_core.views.ACPPlansView.as_view(), name='acp_plans_view'),
    path('cards', acp_core.views.ACPCardsView.as_view(), name='acp_cards_view'),
]
