from django.conf.urls import patterns, include, url
from leadgalaxy.forms import EmailAuthenticationForm
from django.contrib.auth.views import password_reset

import leadgalaxy.views

urlpatterns = patterns('',
    url(r'^$', leadgalaxy.views.index, name='index'),
    url(r'^logout$', leadgalaxy.views.logout),

    url(r'^api/(?P<target>[a-z-]+)$', leadgalaxy.views.api),
    url(r'^product/edit/all$', leadgalaxy.views.bulk_edit, name='bulk_edit'),
    url(r'^product/?(?P<tpl>(grid|table))?$', leadgalaxy.views.product, name='product'),
    url(r'^product/(?P<pid>[0-9]+)$', leadgalaxy.views.product_view, name='product_view'),
    url(r'^product/variants/(?P<store_id>[0-9]+)/(?P<pid>[0-9]+)$', leadgalaxy.views.variants_edit, name='variants_edit'),
    url(r'^boards$', leadgalaxy.views.boards, name='boards'),

    url(r'^accounts/register$', leadgalaxy.views.register, name='register'),
    url(r'^accounts/login/$', 'django.contrib.auth.views.login',
        { 'authentication_form': EmailAuthenticationForm }, name='login'),
     url(r'^accounts/password/reset/$', password_reset, {'template_name': 'registration/password_reset.html'}),

)
