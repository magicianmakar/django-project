from django.urls import path

import aliexpress_core.views

urlpatterns = [
    path('oauth', aliexpress_core.views.AuthorizeView.as_view(), name='aliexpress.oauth'),
    path('token', aliexpress_core.views.TokenView.as_view(), name='aliexpress.token'),
]
