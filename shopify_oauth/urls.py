from django.urls import path

import shopify_oauth.views

urlpatterns = [
    path('', shopify_oauth.views.index, name='shopify_index'),
    path('private-label', shopify_oauth.views.private_label_index, name='shopify_private_label_index'),
    path('install/<str:store>', shopify_oauth.views.install, name='shopify_install'),
    path('callback', shopify_oauth.views.callback, name='shopify_callback'),
    path('select', shopify_oauth.views.AccountSelectView.as_view(), name='shopify_account_select'),
]
