from django.conf.urls import patterns, include, url
from leadgalaxy.forms import EmailAuthenticationForm
from django.contrib.auth.views import password_reset

import order_exports.views

urlpatterns = patterns('',
    url(r'^$', order_exports.views.index, name='order_exports_index'),
    url(r'^add/?$', order_exports.views.add, name='order_exports_add'),
    url(r'^edit/(?P<order_export_id>[\d]+)/?$', order_exports.views.edit, name='order_exports_edit'),
    url(r'^delete/(?P<order_export_id>[\d]+)/?$', order_exports.views.delete, name='order_exports_delete'),

)
