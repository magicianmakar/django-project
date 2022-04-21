from django.conf.urls import url

import loopedin_core.views as views

urlpatterns = [
    url(r'^sso$', views.LoopedinSSO.as_view(), name='loopedin_sso'),
]
