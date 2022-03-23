from django.urls import path

import aliexpress_core.views
import home.views

urlpatterns = [
    path('', home.views.HomePageView.as_view(), name='index'),
    path('stores', home.views.HomePageView.as_view(), name='manage_stores'),
    path('settings', home.views.SettingsPageView.as_view(), name='settings'),
    path('<str:store_type>/dashboard', home.views.DashboardView.as_view(), name='dashboard'),
    path('dashboard', home.views.DashboardView.as_view(), name='dashboard'),
    path('goto/page/<str:url_name>', home.views.GotoPage.as_view(), name='goto-page'),
    path('go/aliexpress/<product_id>/', aliexpress_core.views.GotoAliexpress.as_view(), name='goto_aliexpress'),
]
