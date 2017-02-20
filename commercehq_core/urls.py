from django.conf.urls import patterns, url

import commercehq_core.views

urlpatterns = patterns(
    '',
    url(r'^api/(?P<target>[a-z-]+)$', commercehq_core.views.api),
    url(r'^$', commercehq_core.views.index_view, name='index'),
    url(r'^products$', commercehq_core.views.index_view, name='index'),
    url(r'^product/?(?P<tpl>(grid|table))?$', commercehq_core.views.ProductsList.as_view(), name='product'),

)
