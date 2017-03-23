from django.conf.urls import patterns, url

import order_imports.views

urlpatterns = patterns(
    '',
    url(r'^$', order_imports.views.index, name='order_imports_index'),
    url(r'^upload/(?P<store_id>[\d]+)$', order_imports.views.upload, name='order_imports_upload'),
    url(r'^found/$', order_imports.views.found_orders, name='order_imports_found'),
    url(r'^approve$', order_imports.views.approve, name='order_imports_approve'),
)
