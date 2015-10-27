from django.conf.urls import patterns, include, url
from leadgalaxy.forms import EmailAuthenticationForm

import leadgalaxy.views

urlpatterns = patterns('',
    url(r'^$', leadgalaxy.views.index, name='index'),
    url(r'^logout$', leadgalaxy.views.logout),

    url(r'^api/(?P<target>[a-z-]+)$', leadgalaxy.views.api),

    url(r'^accounts/register$', leadgalaxy.views.register, name='register'),
    url(r'^accounts/login/$', 'django.contrib.auth.views.login',
        { 'authentication_form': EmailAuthenticationForm }, name='login'),
)
