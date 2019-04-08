from django.conf.urls import url

import sso_core.views

urlpatterns = [
    url(r'^redirect/challenge$', sso_core.views.redirect, name='sso.redirect'),
    url(r'^validate$', sso_core.views.validate, name='sso.validate'),
]
