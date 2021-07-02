from django.urls import path

import home.views

urlpatterns = [
    path('', home.views.HomePageView.as_view(), name='index'),
    path('stores', home.views.HomePageView.as_view(), name='manage_stores'),
    path('settings', home.views.SettingsPageView.as_view(), name='settings'),
    path('dashboard', home.views.DashboardView.as_view(), name='dashboard'),
    path('goto/page/<str:url_name>', home.views.GotoPage.as_view(), name='goto-page'),
]
