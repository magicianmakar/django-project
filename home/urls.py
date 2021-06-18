from django.urls import path

import home.views

urlpatterns = [
    path('', home.views.HomePageView.as_view(), name='index'),
    path('settings', home.views.SettingsPageView.as_view(), name='settings'),
    path('goto/page/<str:url_name>', home.views.GotoPage.as_view(), name='goto-page'),
]
